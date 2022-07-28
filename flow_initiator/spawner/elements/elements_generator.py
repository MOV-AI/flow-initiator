from flow_initiator.spawner.elements import (
    ProcessElement,
    ContainerLauncher,
    AttachedProcessLauncher,
)
from flow_initiator.spawner.container_tools import Orchestrator


class ElementsGenerator:
    """
    Factory to create new elements
    generates 3 types:
     -  process that runs on the host
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
        self.orchestrator = Orchestrator({"robot_name": robot_name})
        self.network_name = network

    async def elements_generator(self, *args, **kwargs):
        """
        Factory to create running elements
        by params create process/ containers/ process within running containers
        """
        if "conainer_conf" not in kwargs:
            # if there is no image, it will run on the host as a process
            elem = ProcessElement(*args, **kwargs)
        else:
            kwargs.pop("stdin")
            kwargs.pop("stdout")
            kwargs.pop("stderr")
            kwargs.pop("cwd")
            if "network" not in kwargs:
                kwargs["network"] = self.network_name
            if "attach" in kwargs and kwargs["attach"]:
                elem = AttachedProcessLauncher(
                    orchestrator=self.orchestrator, command=args, **kwargs
                )
            else:
                elem = ContainerLauncher(
                    orchestrator=self.orchestrator, command=args, **kwargs
                )
        await elem.run()
        return elem
