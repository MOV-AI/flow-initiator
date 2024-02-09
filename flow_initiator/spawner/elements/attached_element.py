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
        self.running_thread = None
        self.cont_name = self.name
        self.name = self.cmd[self.cmd.index("-n") + 1]
        self.pid = 0
        self.running = False
        self.exec_outputs = None

    @property
    def return_code(self) -> Optional[int]:
        return self.exit_code

    @property
    def eid(self) -> Tuple[str, int]:
        # todo add feature to orchestrator something like docker container top, and filter by CMD
        return self.name, self.pid

    async def is_running(self) -> bool:
        """
        Checks if the container is running

        Returns: True if running, False otherwise

        """
        return self.running

    def check_and_update(self):
        try:

            _, process_list = self._orchestrator.container_execute_command(self.cont_name, "ps aux", user="root")
            process_list = str(process_list).split("\\n")
            for proc in process_list:
                if "-n" in proc:
                    list_proc = proc.split()
                    node_name = list_proc[list_proc.index("-n") + 1]
                    if node_name == self.name:
                        self.pid = list_proc[1]
                        self.running = True
                        return
        except Exception as e:
            self._logger.error(e)
        self.parse_outptus()
        self.running = False
        if self.exit_code is None:
            self.exit_code = 0

    def handler(self):
        """
        runs the container, or start it again if stopped

        Returns: None

        """
        try:
            self.exec_outputs = self._orchestrator.container_execute_command(self.cont_name, self.cmd, detach=True)
            self.parse_outptus()

        except Exception as e:
            self._logger.error(e)
        self.check_and_update()

    def parse_outptus(self):
        if self.exec_outputs is not None:
            self.exit_code, self.output = self.exec_outputs

    async def run(self):
        """
        runs the container, or start it again if stopped

        Returns: None

        """
        self.handler()

    async def kill(self):
        """
        A kill function for stopping
        Returns: None

        """
        self.send_terminate_signal()
        await self.ensure_process_kill()

    def send_terminate_signal(self):
        """
        send SIGTERM to process
        """
        # for attached processes only send kill signals
        self.send_kill_signal()

    def send_kill_signal(self):
        """
        send SIGKILL to process
        """
        kill_cmd = f"kill -9 {self.pid}"
        self._orchestrator.container_execute_command(self.cont_name, kill_cmd)
        self.check_and_update()
