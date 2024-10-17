"""
   Copyright (C) Mov.ai  - All Rights Reserved
   Unauthorized copying of this file, via any medium is strictly prohibited
   Proprietary and confidential

   Developers:
   - Dor Marcous (dor@mova.ai) - 2023
   - Erez Zomer (erez@mov.ai) - 2023
"""
from flow_initiator.spawner.elements import (
    ProcessElement,
    ContainerLauncher,
    AttachedProcessLauncher,
)
from flow_initiator.spawner.container_tools import Orchestrator
from movai_core_shared import envvars


class ElementsFactory:
    """
    Factory to create new elements
    generates 3 types:
     - process that runs on the host
     - container that runs a single node
     - attached process to a running container
    """

    def __init__(self, robot_name: str, network: str):
        """
        Factory constructor for creating new elements
        Args:
            robot_name: robot name, for all nodes
            network: network name, in case of container
        """
        try:
            self.orchestrator = Orchestrator({"robot_name": robot_name})
        except AttributeError:
            self.orchestrator = None
        self.network_name = network

    def update_envvars(self, envvars_dict: dict, name: str):
        """
        Update the envvars of the container, can be override by the user
        Args:
            envvars_dict: dict of envvars to update
        """
        for envvar in dir(envvars):
            if envvar[0].isupper() and envvar not in envvars_dict:
                envvars_dict[envvar] = eval(f"envvars.{envvar}")
        envvars_dict["APP_NAME"] = name
        envvars_dict["HOSTNAME"] = name

    async def generate_element(self, *args, **kwargs):
        """
        Factory to create running elements
        by params create process/ containers/ process within running containers
        """
        if self.orchestrator is None or "container_conf" not in kwargs or len(kwargs["container_conf"]) == 0:
            # if there is no image, it will run on the host as a process
            elem = ProcessElement(*args, node_name=kwargs["node"], **kwargs)
        else:
            kwargs.pop("stdin")
            kwargs.pop("stdout")
            kwargs.pop("stderr")
            kwargs.pop("cwd")
            conf = kwargs["container_conf"]
            self.update_envvars(kwargs["env"], kwargs["node"])
            if "network" not in conf:
                conf["network"] = self.network_name
            if "attach" in conf and conf["attach"]:
                elem = AttachedProcessLauncher(
                    orchestrator=self.orchestrator, command=args, **kwargs
                )
            else:
                elem = ContainerLauncher(
                    orchestrator=self.orchestrator, command=args, **kwargs
                )
        await elem.run()
        return elem

    async def remove_all_containers(self):
        """
        remove all containers
        Returns: None

        """
        if self.orchestrator is None:
            return
        # Todo make it async
        for container in ContainerLauncher.flow_containers:
            self.orchestrator.container_remove(container)
