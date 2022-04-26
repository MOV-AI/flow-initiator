import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

requirements = [
    "aiohttp==3.6.2",
    "aiohttp-cors==0.7.0",
    "aioredis==1.3.0",
    "uvloop==0.14.0",
    "dal==1.0.0.23",
    "movai_core_shared==1.0.0.8",
    "gd_node==1.0.0.6",
]

# TODO Adapt your project configuration to your own project.
# The name of the package is the one to be used in runtime.
# The 'install_requires' is where you specify the package dependencies of your package. They will be automaticly installed, before your package.  # noqa: E501
setuptools.setup(
    name="flow-initiator",
    version="1.0.1-4",
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
    entry_points={},
)
