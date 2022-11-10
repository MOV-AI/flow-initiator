import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

requirements = []

with open("requirements.txt", "r") as fh:
    for line in fh.readlines(): 
        if line != '\n':
            if '\n' in line:
                line = line.rstrip('\n')
            requirements.append(str(line))


setuptools.setup(
    name="flow-initiator",
    version="1.0.1-10",
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
        "console_scripts":[
            "flow_compiler = flow_initiator.tools.flow_compiler:main",
            "flow_initiator = flow_initiator:main",
            "init_local_db = flow_initiator.tools.init_local_db:main"
        ]
        },
)
