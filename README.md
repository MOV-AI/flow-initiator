[![CI - On DEV](https://github.com/MOV-AI/flow-initiator/actions/workflows/TestOnPR.yml/badge.svg?branch=dev)](https://github.com/MOV-AI/flow-initiator/actions/workflows/TestOnPR.yml) [![Deploy - On main/release](https://github.com/MOV-AI/flow-initiator/actions/workflows/DeployOnMergeMain.yml/badge.svg?branch=main)](https://github.com/MOV-AI/flow-initiator/actions/workflows/DeployOnMergeMain.yml)

# flow-initiator
Flow initiator is the node orchestration tool of the MOV.AI platform.
Responsible for executing the flow by launching, killing and monitoring the nodes for
activating and transitioning between the Flow states, for fulfilling the flow logic

> Flow initiator now comes with docker client support


## Usage

The Flow initiator is activated with the following command:

    flow_initiator

> Prerequisites : The flow initiator is depended on 2 packages:
    1) dal
    2) movai_core_shared

Parameters list that can be set through environment variables:




## Development Setup

The complete build process requires 2 steps :
- a python module building step which will create a `.whl` file
- a docker image building step which will create a container image and install the previously built `.whl` file

## build pip module

    rm dist/*
    python3 -m build .

## install pip module locally

    python3 -m venv .testenv
    source .testenv/bin/activate
    python3 -m pip install --no-cache-dir \
    --index-url="https://artifacts.cloud.mov.ai/repository/pypi-experimental/simple" \
    --extra-index-url https://pypi.org/simple \
    ./dist/*.whl

## build docker images

For ROS noetic distribution :

    docker build -t flow_initiator:noetic -f docker/noetic/Dockerfile .


## Basic Run

For ROS noetic distribution :

    docker run -t flow_initiator:noetic

You don't need to worry about the 4th digit, as the CI system does the automatic bump of it.
=======
    docker run -t flow_initiator:noetic

## Development stack

For ROS noetic distribution :

    sudo chmod 777 -Rf  tests/{logs,shared,userspace}
    docker-compose -f tests/docker-compose.yml up --build -d

Cleaning :

    docker-compose -f tests/docker-compose.yml down --remove-orphans --volumes
