"""

   Copyright (C) Mov.ai  - All Rights Reserved
   Unauthorized copying of this file, via any medium is strictly prohibited
   Proprietary and confidential

   Developers:
   - Dor Marcous  (dor@mov.ai) - 2021
"""
import os
from typing import Tuple, Optional
from flow_initiator.spawner.elements import BaseElement
from flow_initiator.spawner.container_tools import Orchestrator

SRC_LOC = os.getenv("MOVAI_SRC_DIR", "/home/")


class ContainerLauncher(BaseElement):
    """
    A class to control containers
    """

    def __init__(self, orchestrator: Orchestrator, *args, **kwargs):
        """
        Start a new container.
        Args:
            kwargs:
             logger : logger object
             cwd (str): specific working directory
             wait (bool) : if to wait for the process to terminate
             container_name: the name of the container
             hostname: alias configuration for the container network
             image: image name for the container
             network: network name for the container
             network_id: network id for the container, instead of network id
             command: optional command to run the container
             ports: open network ports for this container, list of (port: [ip, port])
             auto_remove (bool): if to remove the container, when it's stopped.
             labels (dict): label for the container
             mounts: mounts drive option
             env (list): environment variables for the container
             volumes (dict): volumes to load
             privileged (bool): if to run container in privileged mode
             devices (list): devices to give permission
             network_mode: type of network mode, default "bridge"
             extra_hosts (dict): extra hosts ips to connect the container
             capabilities (list): grant capabilities for the container


        """
        super().__init__(*args, **kwargs)
        # TODO: add check that container_conf containes name, and image
        kwargs.pop("logger")
        self.running_args = dict(kwargs["container_conf"])
        self.running_args["name"] = kwargs["node"]
        self.name =self.running_args["name"]
        self.running_args["env"] = kwargs["env"]
        self._orchestrator = orchestrator
        self.running_args["hostname"] = self.name
        if "command" not in self.running_args:
            self.running_args["command"] = self.commands
            #self.running_args["entrypoint"] = self.commands


    @property
    def return_code(self) -> Optional[int]:
        # todo check new code
        return self._orchestrator.get_container_state(self.name)["ExitCode"]

    @property
    def eid(self) -> Tuple[str, int]:
        # todo check new code
        state = self._orchestrator.get_container_state(self.name)
        return self.name, state["Pid"]

    async def is_running(self) -> bool:
        # todo check new code
        # todo need to check to await for it to end
        return self._orchestrator.get_container_state(self.name)["Running"]

    async def run(self):
        """
        runs the container, or start it again if stopped

        Returns: None

        """
        self._orchestrator.run_container(**self.running_args)

    async def kill(self):
        """
        A kill function for stopping
        Returns: None

        """
        self._orchestrator.container_stop(self.name)
        await self.ensure_process_kill()

    def send_terminate_signal(self):
        """
        send SIGTERM to process
        """
        _, pid = self.eid
        kill_cmd = f"kill -15 {pid}"
        self._orchestrator.container_execute_command(self.name, kill_cmd)

    def send_kill_signal(self):
        """
        send SIGKILL to process
        """
        _, pid = self.eid
        kill_cmd = f"kill -9 {pid}"
        self._orchestrator.container_execute_command(self.name, kill_cmd)
