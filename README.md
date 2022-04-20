# repository-template-python-component

**main branch:** 

[![Deploy - On branch main/release Push](https://github.com/MOV-AI/repository-template-python-component/actions/workflows/DeployOnMergeMain.yml/badge.svg?branch=dev)](https://github.com/MOV-AI/repository-template-python-component/actions/workflows/DeployOnMergeMain.yml)


## [DELETE ME ON INSTANTIATION] Template Description

Template to be used if you are going to create a python component.

This repository will provide you the following:
- Python component with a centrelized handler forwarding the calls to its own objects that will forward with specific behaviour
- Project structure for your source. tests and CI/CD pipelines
- CI/CD that builds, validates and deploys your component to Nexus. The versioning and branching model follows the universal Mov.AI development guidelines.

To adapt the project to your needs, follow the TODOs placed throughout the project source and tests.

## Development Setup

To be able to install packages from our nexus repository:

Possible environments:
- pypi-experimental (unstable and personal use)
- pypi-integration: Internally avaiable (stable. Where you should grab your dependencies from.)
- pypi-edge: Generally avaiable (Source for production purposes.)


Write the following content into your pip.conf(**~/.config/pip/pip.conf**):
```
[global]
index-url = https://artifacts.cloud.mov.ai/repository/<environment>/simple
extra-index-url = https://pypi.org/simple
trusted-host = artifacts.cloud.mov.ai
               pypi.org
```

## Versioning and branching

The branches and meanings:
- branches derived from dev (feature/ or bugfix/): Its where developements should be introduced to. Its lifetime should be as should as the developments time. 
- dev: The most recent version of the code should be here as its the source of the feature branches. The purpose of this branch is the first point of integration from all features.
- main/ main*: The branch where you will find the most stable version of the component. Its a "deploy" of dev version to an internal release. This deploy must create an artifact that is avaiable to all other teams to use it and provide feedback to it.
- branches derived from main (hotfix/): Its where your hotfixes should be implemented. Do not forget to propagate your hotfixes to the other release versions and the main development release line.
![Screenshot from 2021-10-14 16-29-53](https://user-images.githubusercontent.com/84720623/137349613-368ea252-3c05-460c-8eef-20bb6c4b94f4.png)

In terms of versioning, we basically use semantic versioning but with a 4th digit, automatic incremented by our CI systems:
**{Major}.{Minor}.{Patch}.{buildid}**

If your component has a straight relation with a centralized system, we suggest keeping a relation with it in terms of major,minor and patch to ease support.

## Testing

To run the tests locally, you simply execute:
- python3 -m pytest

## Component packaging
The python component is packaged through the python module **build** and published by the twine **framework**

python3 -m build

python3 -m twine upload -r nexus dist/*

## Component version bumping
To bump the version you can use the **bump2version** framework. Simply in your repository root execute:

bump2version **\<version section>**

version section can be:
- major
- minor
- patch

You don't need to worry about the 4th digit, as the CI system does the automatic bump of it.
