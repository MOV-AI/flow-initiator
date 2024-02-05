import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

requirements = [
    "aioredis==1.3.1",
    "uvloop==0.14.0",
    "movai-core-shared==2.4.1.36",
    "data-access-layer==2.4.1.37",
    "gd-node==2.4.1.24",
]


setuptools.setup(
    name="flow-initiator",
    version="2.4.1-54",
    author="Backend team",
    author_email="backend@mov.ai",
    description="Dummy description",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/MOV-AI/flow-initiator",
    packages=setuptools.find_packages(),
    include_package_data=True,
    classifiers=["Programming Language :: Python :: 3"],
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "flow_compiler = flow_initiator.tools.flow_compiler:main",
            "flow_initiator = flow_initiator:main",
            "init_local_db = flow_initiator.tools.init_local_db:main"
        ]
        },
)
