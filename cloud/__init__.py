import json
import sys
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Optional, List

import requests


class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        # 👇️ if passed in object is instance of Decimal
        # convert it to a string
        if isinstance(obj, Decimal):
            return str(obj)
        # 👇️ otherwise use the default behavior
        return json.JSONEncoder.default(self, obj)


@dataclass
class VMPrice:
    currency_type: Optional[str]
    one_yr_res_per_hr: Optional[Decimal]
    three_yr_res_per_hr: Optional[Decimal]
    spot_price_per_hr: Optional[Decimal]
    price_per_hr: Optional[Decimal]
    region: str

    def json(self):
        return {
            "currency_type": self.currency_type,
            "one_yr_res_per_hr": self.one_yr_res_per_hr,
            "three_yr_res_per_hr": self.three_yr_res_per_hr,
            "spot_price_per_hr": self.spot_price_per_hr,
            "price_per_hr": self.price_per_hr,
            "region": self.region
        }


class PhotonSku(Enum):
    NO_PHOTON = "NO_PHOTON"
    PHOTON_JOBS = "PHOTON_JOBS"
    PHOTON_INTERACTIVE = "PHOTON_INTERACTIVE"


@dataclass
class PhotonMultiplier:
    job_dbu_multiplier: float
    interactive_dbu_multiplier: float


@dataclass
class VMPricePerDBU:
    currency_type: Optional[str]
    one_yr_res_per_dbu: Optional[Decimal]
    three_yr_res_per_dbu: Optional[Decimal]
    spot_price_per_dbu: Optional[Decimal]
    price_per_dbu: Optional[Decimal]
    region: str
    sku: str

    @classmethod
    def from_vm_info(cls, vm_info: 'VMInfo', sku: PhotonSku = PhotonSku.NO_PHOTON, multiplier: float = 1.0):
        dbus = Decimal(vm_info.dbu_per_hr) * Decimal(multiplier)
        return cls(
            currency_type=vm_info.price.currency_type,
            one_yr_res_per_dbu=(vm_info.price.one_yr_res_per_hr / dbus).quantize(Decimal('1e-4')),
            three_yr_res_per_dbu=(vm_info.price.three_yr_res_per_hr / dbus).quantize(Decimal('1e-4')),
            spot_price_per_dbu=(vm_info.price.spot_price_per_hr / dbus).quantize(Decimal('1e-4')),
            price_per_dbu=(vm_info.price.price_per_hr / dbus).quantize(Decimal('1e-4')),
            region=vm_info.price.region,
            sku=str(sku)
        )

    def json(self):
        return {
            "currency_type": self.currency_type,
            "one_yr_res_per_dbu": self.one_yr_res_per_dbu,
            "three_yr_res_per_dbu": self.three_yr_res_per_dbu,
            "spot_price_per_dbu": self.spot_price_per_dbu,
            "price_per_dbu": self.price_per_dbu,
            "region": self.region,
            "sku": self.sku
        }


@dataclass
class VMInfo:
    name: str
    dbu_per_hr: float
    cpu_cores: int
    memory: int
    price: VMPrice
    dbu_prices: List[VMPricePerDBU]

    def json(self):
        return {
            "name": self.name,
            "dbu_per_hr": self.dbu_per_hr,
            "cpu_cores": self.cpu_cores,
            "memory": self.memory,
            "price": self.price.json(),
            "dbu_prices": [dbu_price.json() for dbu_price in self.dbu_prices]
        }


def get_azure_vm_price(region=None, vm_name=None) -> Optional[VMPrice]:
    hrs_per_year = 8760
    hrs_per_three_years = hrs_per_year * 3
    # Call the Azure Retail Prices API
    response = requests.get(
        f"https://prices.azure.com/api/retail/prices?$filter= armRegionName eq '{region}' and armSkuName eq '{vm_name}'")

    # Set your file location and filename to save your json and excel file
    vm_price = VMPrice(
        currency_type="USD",
        one_yr_res_per_hr=None,
        three_yr_res_per_hr=None,
        spot_price_per_hr=None,
        price_per_hr=None,
        region='eastus2',
    )
    # Add the retail prices returned in the API response to a list
    for i in response.json()['Items']:
        if "windows" in i["productName"].lower() or "low priority" in i["skuName"].lower():
            continue

        if i.get("reservationTerm", "").lower() == "1 year":
            vm_price.one_yr_res_per_hr = Decimal(i['retailPrice'] / hrs_per_year).quantize(Decimal('1e-4'))
        elif i.get("reservationTerm", "").lower() == "3 years":
            vm_price.three_yr_res_per_hr = Decimal(i['retailPrice'] / hrs_per_three_years).quantize(Decimal('1e-4'))
        elif "spot" in i.get("skuName", "").lower():
            vm_price.spot_price_per_hr = Decimal(i['retailPrice']).quantize(Decimal('1e-4'))
        else:
            vm_price.price_per_hr = Decimal(i['retailPrice']).quantize(Decimal('1e-4'))

        vm_price.currency_type = i['currencyCode']

    if vm_price.price_per_hr is None:
        return None
    return vm_price


def read_pkg_file(file):
    try:
        import importlib.resources as pkg_resources
    except ImportError:
        # Try backported to PY<37 `importlib_resources`.
        import importlib_resources as pkg_resources
    import cloud
    return pkg_resources.read_text(cloud, file)


def get_regions():
    # with open("/cloud/regions.json", "r") as f:
    return json.loads(read_pkg_file("regions.json"))


def get_azure_databricks_nodes():
    # with open("/cloud/azure.json") as f:
    #     return json.loads(f.read())
    return json.loads(read_pkg_file("azure.json"))


def get_dbu_prices(vm_info: VMInfo, multiplier: PhotonMultiplier):
    return [VMPricePerDBU.from_vm_info(vm_info),
            VMPricePerDBU.from_vm_info(vm_info, sku=PhotonSku.PHOTON_INTERACTIVE,
                                       multiplier=multiplier.interactive_dbu_multiplier),
            VMPricePerDBU.from_vm_info(vm_info, sku=PhotonSku.PHOTON_JOBS,
                                       multiplier=multiplier.job_dbu_multiplier)]


def get_price(region: str, vm_name: str) -> Optional[VMInfo]:
    azure_vms = get_azure_databricks_nodes()
    all_regions = get_regions()
    assert (region in list(set(all_regions["azure"]))), "Not a valid region!"
    if vm_name in azure_vms:
        azure_photon_multiplier = PhotonMultiplier(job_dbu_multiplier=2.5, interactive_dbu_multiplier=2.3)
        price = get_azure_vm_price(region, vm_name=vm_name)
        vm_info = VMInfo(
            **azure_vms[vm_name],
            name=vm_name,
            price=price,
            dbu_prices=[]
        )
        vm_info.dbu_prices = get_dbu_prices(vm_info, azure_photon_multiplier)
        return vm_info

    return None
