# flow-initator
Flow initiator is the node orchistration tool of the MOV.AI platform. 
Respnsible for executing the flow by lunching killing and monitoring the nodes for 
activating and transisining between the Flow states, for fulfilling the flow logic

## Usage

The Flow initiator is activated with the follwoing command: 

    python3 -m flow_initiator

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

For ROS melodic distribution :

    docker build -t flow_initiator:melodic -f docker/melodic/Dockerfile .


For ROS noetic distribution :

    docker build -t flow_initiator:noetic -f docker/noetic/Dockerfile .


## Basic Run

For ROS melodic distribution :

    docker run -t flow_initiator:melodic

For ROS noetic distribution :


You don't need to worry about the 4th digit, as the CI system does the automatic bump of it.
=======
    docker run -t flow_initiator:noetic

## Development stack

For ROS melodic distribution :

    export FLOW_INITIATOR_DISTRO=melodic
    docker-compose -f tests/docker-compose.yml up -d

For ROS noetic distribution :

    export FLOW_INITIATOR_DISTRO=noetic
    docker-compose -f tests/docker-compose.yml up -d




