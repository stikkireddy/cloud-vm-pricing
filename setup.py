from setuptools import setup, find_packages


setup(
    name="cloud-vm-pricing",
    author="Sri Tikkireddy",
    author_email="sri.tikkireddy@databricks.com",
    description="cloud vm pricing",
    long_description_content_type="text/markdown",
    packages=find_packages(exclude=['tests', 'tests.*', ]),
    use_scm_version={
        "local_scheme": "dirty-tag"
    },
    setup_requires=['setuptools_scm'],
    install_requires=[
        'requests>=2.17.3',
    ],
    package_data={'': ['azure.json', 'regions.json']},
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
)
