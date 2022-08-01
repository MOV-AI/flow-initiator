"""

   Copyright (C) Mov.ai  - All Rights Reserved
   Unauthorized copying of this file, via any medium is strictly prohibited
   Proprietary and confidential

   Developers:
   - Dor Marcous  (dor@mov.ai) - 2021
"""
from typing import Tuple, Optional
from movai_core_shared.exceptions import CommandError
from flow_initiator.spawner.elements import ContainerLauncher

DEFAULT_LABELS = None


class AttachedProcessLauncher(ContainerLauncher):
    """
    A class to control containers
    """

    def __init__(self, *args, **kwargs):
        """
        Start a new container.
        Args:
            kwargs:
             logger : logger object
             cwd (str): specific working directory
             wait (bool) : if to wait for the process to terminate
             name: the name of the container
             command: optional command to run the container
             env (list): environment variables for the container

        """
        super().__init__(*args, **kwargs)
        if "command" not in self.running_args:
            raise CommandError(f"Missing command when attaching process in a running container: {self.name}")
        self.cmd = self.running_args["command"]
        self.exit_code = None
        self.output = None

    @property
    def return_code(self) -> Optional[int]:
        return self.exit_code

    @property
    def eid(self) -> Tuple[str, int]:
        # todo add feature to orchestrator something like docker container top, and filter by CMD
        state = self._orchestrator.get_container_state(self.name)
        return self.name, state["Pid"]

    async def is_running(self) -> bool:
        return self.exit_code is None

    async def run(self):
        """
        runs the container, or start it again if stopped

        Returns: None

        """
        exec_outputs = self._orchestrator.container_execute_command(self.name, self.cmd)
        if exec_outputs is not None:
            self.exit_code, self.output = exec_outputs
        else:
            self._logger.error(f"container {self.name} isn't running can't attach")

    async def kill(self):
        """
        A kill function for stopping
        Returns: None

        """
        _, pid = self.eid
        kill_cmd = f"kill {pid}"
        self._orchestrator.container_execute_command(self.name, kill_cmd)
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
