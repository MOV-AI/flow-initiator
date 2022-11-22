"""
   Copyright (C) Mov.ai  - All Rights Reserved
   Unauthorized copying of this file, via any medium is strictly prohibited
   Proprietary and confidential

   Developers:
   - Manuel Silva (manuel.silva@mov.ai) - 2020
   - Tiago Paulino (tiago@mov.ai) - 2020
"""
import asyncio
import concurrent.futures
import os
import re
import pickle
import signal
import tempfile
import time
from asyncio.subprocess import Process
from subprocess import SubprocessError

from movai_core_shared.envvars import APP_LOGS, ENVIRON_ROS2
from movai_core_shared.logger import Log
from movai_core_shared.consts import (
    ROS2_LIFECYCLENODE,
    TIMEOUT_PROCESS_SIGINT,
    TIMEOUT_PROCESS_SIGTERM,
)

from dal.models.lock import Lock
from dal.scopes.package import Package
from dal.scopes.robot import Robot
from dal.models.var import Var


try:
    # Todo: check if we can remove ros1 dependency
    from gd_node.protocols.ros1 import ROS1

    gdnode_exist = True
except ImportError:
    gdnode_exist = False

from .flowmonitor import FlowMonitor
from movai_core_shared.exceptions import CommandError, ActiveFlowError
from .validation import CommandValidator


class Spawner(CommandValidator):
    """Spawns process"""

    EMERGENCY_FLAG = False

    def __init__(self, loop: asyncio.AbstractEventLoop, robot: Robot, debug: bool = False):
        self._logger = Log.get_logger("spawner.mov.ai")
        self._stdout = open(f"{APP_LOGS}/stdout", "w")
        self.loop = loop
        self.lock = asyncio.Lock(loop=self.loop)
        self.robot = robot
        self.debug = debug
        self.temp_dir = tempfile.TemporaryDirectory()
        self.flow_monitor = FlowMonitor()
        self.acq_locks = {}
        self.nodes_to_skip = []

        # commands to interact with the spawner
        self.commands = {
            "START": self.process_start,
            "STOP": self.process_stop,
            "TRANS": self.process_transition,
            "LOCK": self.process_lock,
            "UNLOCK": self.process_unlock,
            "RUN": self.process_run,
            "KILL": self.process_kill,
            "HELP": self.process_help,
            "EMERGENCY_SET": self.process_emergency_set,
            "EMERGENCY_UNSET": self.process_emergency_unset,
        }
        self.commands_help = {
            "START": "command='START', flow='flow_name'",
            "STOP": "command='STOP', flow='flow_name'",
            "TRANS": "command='TRANS', node='node_name', port='port_name'",
            "LOCK": "command='LOCK', data={data}",
            "UNLOCK": "command='UNLOCK', data={data}",
            "RUN": "command='RUN', node='node_name'",
            "KILL": "command='KILL', node='node_name', dependencies=bool",
            "HELP": "command='HELP'",
            "EMERGENCY_SET": "command='EMERGENCY_SET', data={'nodes_to_skip': [<regex>]}",
            "EMERGENCY_UNSET": "command='EMERGENCY_UNSET'",
        }
        # core processes launched   {"ProcessName": { "process": proc, "pid": pid}}
        self.core_lchd = {}
        # nodes launched            {"NodeInst"   : { "process": proc, "pid": pid}}
        self.nodes_lchd = {}
        # persistent nodes launched {"NodeInst"   : { "process": proc, "pid": pid}}
        self.persistent_nodes_lchd = {}
        self.active_states = set()

        # When waking up the Robot needs to launch the boot flow when configured

        initial_state = self.robot.get_states().get("boot", None)
        if initial_state:
            flow_name = initial_state.get("flow", "")
            self.loop.create_task(self.process_start(command="START", flow=flow_name))

    def should_skip_node(self, node_name):
        """indicated whether to skip specific node from killing while pressing emergency button"""

        for regex_object in self.nodes_to_skip:
            if regex_object.match(node_name) is not None:
                return True
        return False

    def reset_emergency_params(self):
        """reset EMERGENCY params"""
        if type(self).EMERGENCY_FLAG:
            self._logger.info("UNSET EMERGENCY_FLAG")
        type(self).EMERGENCY_FLAG = False
        self.nodes_to_skip = []

    async def fn_update_robot(self) -> None:
        """Collects robot parameters and executes the update in a separate thread"""

        data = {
            "active_flow": getattr(self.flow_monitor.active_flow, "path", ""),
            "nodes_lchd": [key for key in self.nodes_lchd],
            "persistent_nodes_lchd": [key for key in self.persistent_nodes_lchd],
            "active_states": list(self.active_states),
            "core_lchd": [key for key in self.core_lchd],
            "locks": Lock.enabled_locks,
            "timestamp": time.time(),
        }
        active_scene = self.robot.Status.get("active_scene", "") if data["active_flow"] else ""
        data.update({"active_scene": active_scene})

        # run robot update in a thread executor so it does not block
        await self.loop.run_in_executor(None, self.th_robot_update, self.robot.name, data)

    def th_robot_update(self, robot_name: str, data: dict) -> None:
        """robot update blocks, should run in a thread executor"""
        Robot.cls_update_status(robot_name, data, db="all")

    async def stop(self) -> None:
        """Stop all processes"""

        self._logger.debug("Spawner: terminating processes.")

        self.flow_monitor.active_flow = None
        self.persistent_nodes_lchd = {}
        self.nodes_lchd = {}
        self.core_lchd = {}
        self.active_states = set()
        await self.fn_update_robot()

        processes = {}
        processes.update(self.core_lchd)
        processes.update(self.nodes_lchd)
        processes.update(self.persistent_nodes_lchd)

        tasks = []
        for node_name, value in processes.items():
            tasks.append(self.terminate_process(value, node_name))
        # wait for all get_keys tasks to run
        _values = await asyncio.gather(*tasks)

        # Release active locks
        for key in list(self.acq_locks.keys()):
            Lock(**self.acq_locks.pop(key)).release()

    async def stop_flow(self) -> None:
        """Stop active flow"""

        self._logger.debug("Spawner: terminating active flow.")

        processes = {}
        processes.update(self.nodes_lchd)
        processes.update(self.persistent_nodes_lchd)

        tasks = []
        for node_name, value in processes.items():
            tasks.append(self.terminate_process(value, node_name))
        # wait for all get_keys tasks to run
        _values = await asyncio.gather(*tasks)
        if gdnode_exist:
            # need to check all nodes are dead before cleaning parameter server cuz dyn req
            ROS1.clean_parameter_server()
            # Clean dead nodes still registered in ros master
            ROS1.rosnode_cleanup()

        # Clean all Flow Vars
        Var.delete_all(scope="Flow")

        self._logger.info("Spawner: flow terminated.")
        self.flow_monitor.unload()
        self.persistent_nodes_lchd = {}
        self.nodes_lchd = {}
        self.active_states = set()

        # Release active locks if not persistent
        for key in list(self.acq_locks.keys()):

            lock = Lock(**self.acq_locks.pop(key))

            if not lock.persistent:
                lock.release()

    async def await_process(self, process: Process) -> None:
        """Wait for the process to end"""
        pid = process.pid
        try:
            _, stderr_data = await process.communicate()
        except (BrokenPipeError, ConnectionResetError):
            self._logger.info(f"{pid} process terminated.")

        pids = {}
        _ = [
            pids.setdefault("%s" % value["pid"], {"node": key, "ref": self.nodes_lchd})
            for key, value in self.nodes_lchd.items()
        ]
        _ = [
            pids.setdefault("%s" % value["pid"], {"node": key, "ref": self.persistent_nodes_lchd})
            for key, value in self.persistent_nodes_lchd.items()
        ]

        node_name = "unknown"
        if "%s" % pid in pids:
            node_process = pids["%s" % pid]
            node_name = node_process.get("node", "unknown")

            try:
                del node_process["ref"][node_name]
                self.active_states.remove(node_name)
            except KeyError:
                pass

        log_msg = "**  Node {} ({}) terminated with code {}  **".format(
            node_name, pid, process.returncode
        )
        self._logger.info(log_msg) if process.returncode == 0 else self._logger.error(log_msg)

    async def terminate_process(self, process_key: dict, node_name: str) -> None:
        """Terminate process"""
        process = process_key["process"]
        self._logger.info(
            "Spawner: Trying to terminate node {} ({})".format(node_name, process_key["pid"])
        )
        try:
            process.send_signal(signal.SIGINT)
        except ProcessLookupError:
            pass

        await self.ensure_process_kill(process_key, node_name)

    async def ensure_process_kill(self, process_key: dict, node_name: str) -> None:
        """Ensure the process dies"""
        # process.terminate() -> Send SIGTERM
        # process.kill()      -> Send SIGKILL
        timeout_int = TIMEOUT_PROCESS_SIGINT
        timeout_term = TIMEOUT_PROCESS_SIGTERM

        sigterm_sent = False

        pid = process_key["pid"]
        process = process_key["process"]

        t_init = time.time()
        while 1:
            current_time = time.time()
            return_code = process.returncode

            if return_code is not None:
                return return_code

            if current_time > t_init + timeout_int:
                if not sigterm_sent:
                    self._logger.error(
                        "Sending SIGTERM to node {} ({})".format(node_name, str(pid))
                    )
                    process.terminate()
                    sigterm_sent = True

            if current_time > t_init + timeout_int + timeout_term:
                self._logger.error("Sending SIGKILL to node {} ({})".format(node_name, str(pid)))
                process.kill()
                return None
            await asyncio.sleep(0.2)

    async def launch_process(
        self,
        command: tuple,
        wait: bool = True,
        add_to: str = None,
        cwd: str = None,
        env: list = None,
    ) -> None:
        """Launch process, add to list and create task to wait for its end"""
        self._logger.info(
            ("Launching command (persistent: {}) {}".format(command[2], " ".join(command[1])))
        )
        # self._logger.debug(f"Environment vars: %s) {env}")
        cwd = cwd or self.temp_dir.name
        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(
                *command[1],
                stdin=None,
                stdout=self._stdout,
                stderr=self._stdout,
                cwd=cwd,
                env=env,
            )

            if add_to is not None:
                getattr(self, add_to)[command[0]] = {"process": proc, "pid": proc.pid}
            else:
                if command[2]:  # is node persistent
                    getattr(self, "persistent_nodes_lchd")[command[0]] = {
                        "process": proc,
                        "pid": proc.pid,
                    }
                else:
                    getattr(self, "nodes_lchd")[command[0]] = {
                        "process": proc,
                        "pid": proc.pid,
                    }
            if command[3]:
                self.active_states.add(command[0])
            # self._logger.info(("{}-PID: {}".format(command[0], proc.pid)))
            if wait:
                self.loop.create_task(self.await_process(proc))
        except (SubprocessError, OSError, ValueError, TypeError) as e:
            self._logger.critical("An error occurred while starting a flow, see errors")
            self._logger.critical(e)
            if proc is not None:
                proc.kill()
            return

    async def process_command(self, command_str: bytes) -> None:
        """Parse received command and trigger callback"""
        # command_str ex.: command=START&flow=flow_name&node=node_name

        _params = pickle.loads(command_str)

        # using only one value per parameter
        # convert {param_name: [value], ...} to {param_name: value, ...}
        params = {}
        [params.setdefault(key, value) for key, value in _params.items()]

        if params.get("command", None) is None:
            self._logger.error("Command not found. Push 'command=HELP' to get available commands.")
            return

        # get command callback
        # func = self.commands.get(params["command"], None)
        # if func:
        #     self.loop.create_task(func(**params))
        try:
            await self.lock.acquire()

            self.validate_command(**params, active_flow=self.flow_monitor.active_flow)

            await self.commands[params["command"]](**params)
        except (CommandError, ActiveFlowError) as e:
            self._logger.warning(str(e))
        finally:
            self.lock.release()

    async def process_help(self, _):
        """Process command HELP. Only visible in debug mode or in the log file"""
        self._logger.info("{:^72}".format(" *** AVAILABLE COMMANDS *** "))
        for command, value in self.commands_help.items():
            self._logger.info("{:>14}: {}".format(command, value))
        self._logger.info("{:^72}".format(" ************************** "))

    async def process_start(self, **kwargs):
        """Process command START"""
        self.reset_emergency_params()
        command = kwargs.get("command", None)
        flow = kwargs.get("flow", None)
        if not all([command, flow]):
            self._logger.error(
                "START command failed. Format is {}. Other parameters ignored.".format(
                    self.commands_help["START"]
                )
            )
            return

        if self.flow_monitor.active_flow is not None:
            # task = self.loop.create_task(self.stop_flow())
            # await asyncio.wait([task])
            await self.stop_flow()

        if self.flow_monitor.active_flow is None:
            self._logger.info("START flow {}".format(kwargs["flow"]))
            commmands_to_launch = self.flow_monitor.load(flow)
            if len(commmands_to_launch) == 0:
                # nothing to launch
                return

            # Clean all Flow Vars
            Var.delete_all(scope="Flow")

            # Lifecycle Nodes will be launched in the beginning, if they are starting nodes
            # they also need to be activated
            ros2_lifecycle_nodes_to_activate = []
            for lc_node in self.flow_monitor.load_ros2_lifecycle():
                if lc_node[0] not in [command[0] for command in commmands_to_launch]:
                    commmands_to_launch.append(lc_node)
                else:
                    ros2_lifecycle_nodes_to_activate.append(lc_node[0])

            # self._logger.info(commmands_to_launch)

            tasks = []
            try:
                for command in commmands_to_launch:
                    packages = self.flow_monitor.get_node_packages(command[0])
                    await self.dump_packages(packages)
                    tasks.append(
                        self.loop.create_task(
                            self.launch_process(command, wait=True, env=command[4])
                        )
                    )

                # wait until all are launched
                await asyncio.gather(*tasks, loop=self.loop)
            except (SubprocessError, OSError, ValueError, TypeError) as e:
                self._logger.critical("An error occurred while starting a flow, see errors")
                self._logger.critical(e)
                for task in tasks:
                    task.cancel()
                await self.stop_flow()
                return
            # Configure all Ros2 lifecycle nodes
            for node_name in self.flow_monitor.get_lifecycle_nodes():
                cmd = ["ros2", "lifecycle", "set", node_name, "configure"]
                await self.ros2_lifecycle(node_name, cmd)

            # Activate the starting Ros2 lifecycle nodes
            for node_name in ros2_lifecycle_nodes_to_activate:
                cmd = ["ros2", "lifecycle", "set", node_name, "activate"]
                await self.ros2_lifecycle(node_name, cmd)

    async def process_stop(self, **kwargs):
        """Process command STOP"""
        self.reset_emergency_params()
        command = kwargs.get("command", None)
        flow = kwargs.get("flow", None)
        if not all([command, flow]):
            self._logger.error(
                "STOP command failed. Format is {}. Other parameters ignored.".format(
                    self.commands_help["STOP"]
                )
            )
            return
        if self.flow_monitor.active_flow is not None:
            self._logger.info("STOP flow {}".format(kwargs["flow"]))
            # self.loop.create_task(self.stop_flow())
            await self.stop_flow()
        else:
            self._logger.error("No flow active. START a flow first.")

    async def process_transition(self, **kwargs):
        """Process command TRANS"""
        command = kwargs.get("command", None)
        node = kwargs.get("node", None)
        port = kwargs.get("port", None)
        data = kwargs.get("data", None)

        # check if the transition is coming from the current active flow
        ctx_flow = kwargs.get("flow", None)
        if ctx_flow != self.flow_monitor.active_flow.Label:
            self._logger.error(
                f"Transition from node '{node}'' in flow '{ctx_flow}' blocked. Flow '{ctx_flow}' is not running."
            )
            return

        trans_msg = pickle.dumps(data)
        if type(self).EMERGENCY_FLAG and not self.should_skip_node(node):
            self._logger.warning("EMERGENCY button was pressed, Terminating transition!!")
            return

        if not all([command, node, port]):
            self._logger.error(
                "TRANS command failed. Format is {}. Other parameters ignored.".format(
                    self.commands_help["TRANS"]
                )
            )
            return
        self._logger.info("TRANS from node: {}   port: {}".format(node, port))
        if self.flow_monitor.active_flow is None:
            self._logger.error("No flow active. START a flow first.")
            return

        commmands_to_launch = self.flow_monitor.transition(
            node, port, self.active_states, transition_msg=trans_msg
        )

        if len(set.difference(self.active_states, {node})) + len(commmands_to_launch) == 0:
            # if after stopping the node, we are left with not state nodes,
            # it's time to die
            return await self.stop_flow()

        all_nodes_to_launch = [command[0] for command in commmands_to_launch]
        nodes_to_kill = [node for node in self.nodes_lchd if node not in all_nodes_to_launch]
        nodes_to_launch = [
            node
            for node in all_nodes_to_launch
            if node not in self.nodes_lchd and node not in self.persistent_nodes_lchd
        ]

        # In case of emergency flag do not launch not allowed nodes
        if type(self).EMERGENCY_FLAG:
            nodes_allowed_to_launch = [
                node for node in nodes_to_launch if self.should_skip_node(node)
            ]
            if nodes_allowed_to_launch != nodes_to_launch:
                self._logger.warning(
                    "EMERGENCY button was pressed, not launching nodes: {}".format(
                        ", ".join(set(nodes_to_launch) - set(nodes_allowed_to_launch))
                    )
                )
            nodes_to_launch = nodes_allowed_to_launch

        # In case of emergency flag do not launch not allowed nodes
        if type(self).EMERGENCY_FLAG:
            nodes_allowed_to_launch = [
                node for node in nodes_to_launch if self.should_skip_node(node)
            ]
            if nodes_allowed_to_launch != nodes_to_launch:
                self._logger.warning(
                    "EMERGENCY button was pressed, not launching nodes: {}".format(
                        ", ".join(set(nodes_to_launch) - set(nodes_allowed_to_launch))
                    )
                )
            nodes_to_launch = nodes_allowed_to_launch

        for node_name in nodes_to_kill:
            if self.flow_monitor.get_node_type(node_name) == ROS2_LIFECYCLENODE:
                cmd = ["ros2", "lifecycle", "set", node_name, "deactivate"]
                await self.ros2_lifecycle(node_name, cmd)
            else:
                node_to_kill = self.nodes_lchd[node_name]
                self.loop.create_task(self.terminate_process(node_to_kill, node_name))

        tasks = []
        for command in commmands_to_launch:
            if command[0] in nodes_to_launch:
                packages = self.flow_monitor.get_node_packages(command[0])
                await self.dump_packages(packages)
                # launch process
                # self._logger.info(("command in process_command:{}/{}/{}".format(command[0], command[2], command[1])))
                tasks.append(
                    self.loop.create_task(self.launch_process(command, wait=True, env=command[4]))
                )

        if type(self).EMERGENCY_FLAG and not self.should_skip_node(node):
            for task in tasks:
                task.cancel()
            return

        await asyncio.gather(*tasks, loop=self.loop)

        # activate Ros2 lifecycle nodes that are already launched
        for node_name in all_nodes_to_launch:
            if (
                node_name in self.nodes_lchd
                and self.flow_monitor.get_node_type(node_name) == ROS2_LIFECYCLENODE
            ):
                cmd = ["ros2", "lifecycle", "set", node_name, "activate"]
                await self.ros2_lifecycle(node_name, cmd)

    async def process_lock(self, **kwargs):
        """
        Process command LOCK
        This command enables Lock heartbeat for a specific Lock
        """

        try:
            data = kwargs.get("data", {})

            self.acq_locks.update({data.get("name"): data})
            self.loop.create_task(Lock.enable_heartbeat(**data))

        except Exception as e:
            self._logger.error(f"Error while processing LOCK command {str(e)}")

    async def process_unlock(self, **kwargs):
        """
        Process command UNLOCK
        This command disables Lock heartbeat for a specific Lock
        """

        data = kwargs.get("data", {})

        try:
            Lock.disable_heartbeat(**data)

        except Exception as e:
            self._logger.error(f"Error while processing UNLOCK command {str(e)}")

        finally:

            try:
                self.acq_locks.pop(data.get("name", ""))

            except KeyError:
                pass

    async def process_run(self, **kwargs):
        """
        Process command RUN
        It Runs a Node Inst and all its dependencies
        """
        command = kwargs.get("command", None)
        node = kwargs.get("node", None)
        if not all([command, node]):
            self._logger.error(
                "RUN command failed. Format is {}. Other parameters ignored.".format(
                    self.commands_help["RUN"]
                )
            )
            return

        commmands_to_launch = self.flow_monitor.get_commands([node], self.flow_monitor.active_flow)
        all_nodes_to_launch = [command[0] for command in commmands_to_launch]

        nodes_to_launch = [
            node
            for node in all_nodes_to_launch
            if node not in self.nodes_lchd and node not in self.persistent_nodes_lchd
        ]

        if not nodes_to_launch:
            self._logger.warning("Node {} is already launched or was not found".format(node))
            return

        self._logger.debug(f"RUN node {node}")

        tasks = []
        for command in commmands_to_launch:
            if command[0] in nodes_to_launch:
                tasks.append(
                    self.loop.create_task(self.launch_process(command, wait=True, env=command[4]))
                )
        await asyncio.gather(*tasks, loop=self.loop)

    async def process_kill(self, **kwargs):
        """
        Process command KILL
        It Kills a Node Inst and all its dependencies (if flag dependencies is true)
        """
        command = kwargs.get("command", None)
        node = kwargs.get("node", None)
        # TODO: option to kill dependencies
        # dependencies = kwargs.get("dependencies", False)

        if not all([command, node]):
            self._logger.error(
                f"KILL command failed. Format is {self.commands_help['KILL']}."
                f"Other parameters ignored."
            )
            return

        self._logger.debug(f"KILL node {node}")

        process = self.nodes_lchd.get(node, None) or self.persistent_nodes_lchd.get(node, None)

        if process is None:
            self._logger.warning("Could not kill Node {} because is not launched".format(node))
            return

        await self.terminate_process(process, node)

    async def ros2_lifecycle(self, node_name: str, command):
        """Handles ROS2 Lifecycle managed nodes
        create, configure, cleanup, activate, deactivate, shutdown, destroy
        """
        self._logger.info("Spawner: ROS2 Lifecycle command{}".format(command))
        _stdout = None
        await asyncio.create_subprocess_exec(
            *command, stdin=None, stdout=_stdout, env=ENVIRON_ROS2
        )

    async def dump_packages(self, packages: list):
        """Dump package files"""
        # packages: [{"name": package_name, "file": file_name, "path": package_relative_path}, ...]
        dumps = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:

            for package in packages:

                package_name = package.get("package", None)
                if package_name is not None:
                    try:
                        pack = Package(package_name)

                        file_name = package.get("file", None)
                        dir_path = "/".join([self.temp_dir.name, package.get("path")])

                        if file_name not in [None, ""]:
                            # dump only requested file
                            files = [file_name]
                        else:
                            # dump all files in Package
                            files = list(pack.File.keys())

                        for file_name in files:
                            # file_name: name or folder1/folder2/name
                            file_el = file_name.split("/")

                            # get everything except the file name
                            path = "/".join(file_el[:-1])

                            file_path = dir_path
                            if path != "":
                                file_path = "/".join([dir_path, path])

                            if not os.path.exists(file_path):
                                os.makedirs(file_path)

                            dumps.append(
                                self.loop.run_in_executor(
                                    executor,
                                    Package.dump,
                                    package_name,
                                    file_name,
                                    str.join("/", [file_path, file_el[-1]]),
                                )
                            )

                    except Exception as error:
                        self._logger.error(str(error))
                        continue

            # nothing to dump
            if not dumps:
                return

            # await for tasks execution in the executor
            self._logger.info(f"Dumping files...{packages}")
            completed, _ = await asyncio.wait(dumps)
            results = [t.result() for t in completed]
            invalids = [
                (result, file_name, checksum)
                for result, file_name, checksum in results
                if result is False
            ]
            if invalids:
                msg_invalid_checksum = "Checksum {} for file {} is invalid."
                for result, file_name, checksum in invalids:
                    self._logger.critical(msg_invalid_checksum.format(checksum, file_name))

    async def process_emergency_set(self, **kwargs):
        """activates EMERGENCY button pressed, all active states will be killed unless it matches
        a specific pattern provided in data in kwargs"""
        data = kwargs.get("data", {})
        self._logger.info("EMERGENCY BUTTON PRESSED, SET EMERGENCY_FLAG = True")
        type(self).EMERGENCY_FLAG = True

        for regex_str in data.get("nodes_to_skip", []):
            self.nodes_to_skip.append(re.compile(regex_str))

        tasks = []
        for node_name in self.active_states:
            if self.should_skip_node(node_name):
                continue
            kwargs_local = {"command": "KILL", "node": node_name}
            tasks.append(self.process_kill(**kwargs_local))

        # wait for all get_keys tasks to run
        await asyncio.gather(*tasks)

    async def process_emergency_unset(self, _):
        """deactivate EMERGENCY button, unsetting relevant flags"""
        self.reset_emergency_params()
