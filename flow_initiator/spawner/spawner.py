"""
   Copyright (C) Mov.ai  - All Rights Reserved
   Unauthorized copying of this file, via any medium is strictly prohibited
   Proprietary and confidential

   Developers:
   - Manuel Silva (manuel.silva@mov.ai) - 2020
   - Tiago Paulino (tiago@mov.ai) - 2020
   - Dor Marcous (dor@mova.ai) - 2021
"""
import asyncio
import concurrent.futures
import os
import re
import pickle
import tempfile
import time
from typing import Union
from subprocess import SubprocessError

from beartype import beartype

from dal.helpers.cache import ThreadSafeCache
from dal.models.lock import Lock
from dal.models.var import Var
from dal.scopes.package import Package
from dal.scopes.robot import Robot

from movai_core_shared.consts import ROS2_LIFECYCLENODE
from movai_core_shared.envvars import APP_LOGS, ENVIRON_ROS2
from movai_core_shared.common.utils import is_enterprise
from movai_core_shared.logger import Log
from movai_core_shared.exceptions import CommandError, RunError

from flow_initiator.spawner.elements import ElementsFactory, BaseElement


try:
    # Todo: check if we can remove ros1 dependency
    from gd_node.protocols.ros1 import ROS1

    gdnode_exist = True
except ImportError:
    gdnode_exist = False

from .flowmonitor import FlowMonitor
from .validation import CommandValidator


NETWORK_PREFIX = os.getenv("NETWORK_PREFIX", "MovaiNetwork")


class Spawner:
    """Spawns elements"""

    EMERGENCY_FLAG = False

    @beartype
    def __init__(self, robot: Robot, debug: bool = False, network: str = None):
        """
        Flow initator constructor

        Args:
            robot (Robot): robot object
            debug (bool, optional): debug mode flag, default to False.
            network (str, optional): The docker network name
        """
        self._logger = Log.get_logger("spawner.mov.ai")
        self._stdout = open(f"{APP_LOGS}/stdout", "w")
        self._lock = None
        self.robot = robot
        if network is None:
            if is_enterprise():
                network = f"{NETWORK_PREFIX}-{robot.RobotName}-movai"
            else:
                network = "flow-private"
        self.factory = ElementsFactory(robot_name=robot.RobotName, network=network)
        self.temp_dir = tempfile.TemporaryDirectory()
        self.flow_monitor = FlowMonitor()
        self.acq_locks = {}
        self.nodes_to_skip = []

        # commands to interact with the spawner
        self.commands = CommandValidator(
            {
                "START": [self.process_start, "command='START', flow='flow_name'"],
                "STOP": [self.process_stop, "command='STOP', flow='flow_name'"],
                "TRANS": [
                    self.process_transition,
                    "command='TRANS', node='node_name', port='port_name'",
                ],
                "LOCK": [self.process_lock, "command='LOCK', data={data}"],
                "UNLOCK": [self.process_unlock, "command='UNLOCK', data={data}"],
                "RUN": [self.process_run, "command='RUN', node='node_name'"],
                "KILL": [
                    self.process_kill,
                    "command='KILL', node='node_name', dependencies=bool",
                ],
                "HELP": [self.process_help, "command='HELP'"],
                "EMERGENCY_SET": [
                    self.process_emergency_set,
                    "command='EMERGENCY_SET', data={'nodes_to_skip': [<regex>]}",
                ],
                "EMERGENCY_UNSET": [
                    self.process_emergency_unset,
                    "command='EMERGENCY_UNSET'",
                ],
            }
        )
        # core elements launched
        self.core_lchd = {}
        # nodes launched
        self.nodes_lchd = {}
        # persistent nodes launched
        self.persistent_nodes_lchd = {}
        self.active_states = set()

        # When waking up the Robot needs to launch the boot flow when configured

    def _init_lock(self):
        if self._lock is None:
            asyncio.get_running_loop()
            self._lock = asyncio.Lock()

    def run(self):
        """Starts running the object."""
        self._init_lock()
        initial_state = self.robot.get_states().get("boot", None)
        if initial_state:
            flow_name = initial_state.get("flow", "")
            asyncio.create_task(self.process_start(command="START", flow=flow_name))

    def should_skip_node(self, node_name: str) -> bool:
        """
        indicated whether to skip specific node from killing while pressing emergency button
        Args:
            node_name: the name of the node

        Returns: (bool) if this node should be skipped

        """

        for regex_object in self.nodes_to_skip:
            if regex_object.match(node_name) is not None:
                return True
        return False

    def reset_emergency_params(self):
        """
        reset EMERGENCY params
        """
        if type(self).EMERGENCY_FLAG:
            self._logger.info("UNSET EMERGENCY_FLAG")
        type(self).EMERGENCY_FLAG = False
        self.nodes_to_skip = []

    async def fn_update_robot(self) -> None:
        """
        Collects robot parameters and executes the update in a separate thread
        """

        data = {
            "active_flow": getattr(self.flow_monitor.active_flow, "path", ""),
            "nodes_lchd": [key for key in self.nodes_lchd],
            "persistent_nodes_lchd": [key for key in self.persistent_nodes_lchd],
            "active_states": list(self.active_states),
            "core_lchd": [key for key in self.core_lchd],
            "locks": Lock.enabled_locks,
            "timestamp": time.time(),
        }
        active_scene = (
            self.robot.Status.get("active_scene", "") if data["active_flow"] else ""
        )
        data.update({"active_scene": active_scene})
        self.robot.update_status(data, db="local")

        # run robot update in a thread executor, so it does not block
        await asyncio.get_running_loop().run_in_executor(
            None, self.th_robot_update, self.robot.name, data
        )

    def th_robot_update(self, robot_name: str, data: dict) -> None:
        """robot update blocks, should run in a thread executor"""
        Robot.cls_update_status(robot_name, data, db="global")

    async def stop(self) -> None:
        """
        Stop all elements
        """

        self._logger.debug("Spawner: terminating elements.")

        self.flow_monitor.active_flow = None
        self.active_states = set()
        await self.fn_update_robot()

        elements = {}
        elements.update(self.core_lchd)
        elements.update(self.nodes_lchd)
        elements.update(self.persistent_nodes_lchd)

        tasks = []
        for _, value in elements.items():
            tasks.append(asyncio.create_task(value.kill()))
        # wait for all get_keys tasks to run
        await asyncio.gather(*tasks)
        await self.factory.remove_all_containers()
        self.persistent_nodes_lchd = {}
        self.nodes_lchd = {}
        self.core_lchd = {}
        # Release active locks
        for key in list(self.acq_locks.keys()):
            Lock(**self.acq_locks.pop(key)).release()

    async def stop_flow(self) -> None:
        """
        Stop active flow
        """
        # todo: rm all containers that started in the flow
        self._logger.debug("Spawner: terminating active flow.")

        elements = {}
        elements.update(self.nodes_lchd)
        elements.update(self.persistent_nodes_lchd)

        tasks = []
        for _, element in elements.items():
            tasks.append(element.kill())
        # wait for all get_keys tasks to run
        self.flow_monitor.unload()
        await asyncio.gather(*tasks)
        await self.factory.remove_all_containers()
        if gdnode_exist:
            # need to check all nodes are dead before cleaning parameter server cuz dyn req
            ROS1.clean_parameter_server()
            # Clean dead nodes still registered in ros master
            ROS1.rosnode_cleanup()

        # Clean all Flow Vars
        Var.delete_all(scope="Flow")

        self._logger.info("Spawner: flow terminated.")
        self.persistent_nodes_lchd = {}
        self.nodes_lchd = {}
        self.active_states = set()

        # Release active locks if not persistent
        for key in list(self.acq_locks.keys()):
            lock = Lock(**self.acq_locks.pop(key))

            if not lock.persistent:
                lock.release()

    async def clean_element(self, element: BaseElement, node_name: str) -> None:
        """
        Wait for the element to end
        Args:
            element: the element to wait for
            node_name: node name that running element


        """
        # Todo: make it work for containers
        running = await element.is_running()
        if running:
            self._logger.warning(f"Node: {node_name} is still running")
        if node_name in self.nodes_lchd:
            # Todo: need to here a wait command for container to end
            del self.nodes_lchd[node_name]
        elif node_name in self.persistent_nodes_lchd:
            del self.persistent_nodes_lchd[node_name]
        else:
            self._logger.warning(
                f"can't find element with node name: {node_name} with id: {element.eid_str()}"
            )
        if node_name in self.active_states:
            self.active_states.remove(node_name)

        log_msg = "**  Node {} ({}) terminated with code {}  **".format(
            node_name, element.eid_str(), element.return_code
        )
        if os.strerror(element.return_code) == "Success":
            self._logger.info(log_msg)
        else:
            self._logger.error(log_msg)

    async def launch_element(
        self,
        node: str,
        command: tuple,
        add_to: str = None,
        cwd: str = None,
        env: list = None,
        state: bool = False,
        **kwargs,
    ) -> None:
        """
        Launch element, add to list and create task to wait for its end
        Args:
            command: the running line
            add_to: a specific group
            cwd: current working directory
            env: environment variables
            state: is it a state node

        Returns: None

        """
        persistent = kwargs.pop("persistent", False)
        self._logger.debug(
                "Launching command (persistent: {}) {}".format(persistent, " ".join(command)))
        cwd = cwd or self.temp_dir.name
        elem = None
        try:
            elem = await self.factory.generate_element(
                *command,
                stdin=None,
                stdout=self._stdout,
                stderr=self._stdout,
                cwd=cwd,
                env=env,
                logger=self._logger,
                node=node,
                **kwargs,
            )
            # Todo: maybe add to a specific flow
            if add_to is not None:
                getattr(self, add_to)[node] = elem
            else:
                if persistent:  # is node persistent
                    getattr(self, "persistent_nodes_lchd")[node] = elem
                else:
                    getattr(self, "nodes_lchd")[node] = elem
            if state:
                self.active_states.add(node)
        except (
            SubprocessError,
            OSError,
            ValueError,
            TypeError,
            RunError,
            CommandError,
        ) as e:
            self._logger.critical("An error occurred while starting a flow, see errors")
            self._logger.critical(e)
            if elem is not None:
                await elem.kill()

    async def process_command(self, command_dict: Union[bytes, dict]) -> None:
        """
        Parse received command and trigger callback
        Args:
            command_dict: commands params in dict

        Returns: None

        """
        if type(command_dict) == bytes:
            params = pickle.loads(command_dict)
        else:
            params = command_dict
        if not isinstance(params, dict):
            self._logger.error(
                f"can't parse command {params}, only dict type is acceptable"
            )
            return
        if "command" not in params:
            self._logger.error(
                "Command not found. Push 'command=HELP' to get available commands."
            )
            return

        try:
            await self._lock.acquire()

            self.commands.validate_command(
                **params, active_flow=self.flow_monitor.active_flow
            )

            await self.commands[params["command"]](**params)
        except Exception as e:
            self._logger.critical(str(e))
        finally:
            self._lock.release()

    async def process_help(self, **_):
        """
        Process help command to print out the help menu with all the commands.
        Args:
            _: unused args

        Returns: None

        """
        self._logger.info("{:^72}".format(" *** AVAILABLE COMMANDS *** "))
        self.commands.print_help()
        self._logger.info("{:^72}".format(" ************************** "))

    async def process_start(self, **kwargs):
        """Process command START"""
        self.reset_emergency_params()
        command = kwargs.get("command", None)
        flow = kwargs.get("flow", None)
        if not all([command, flow]):
            self._logger.error(
                "START command failed. Format is {}. Other parameters ignored.".format(
                    self.commands.help("START")
                )
            )
            return

        if self.flow_monitor.active_flow is not None:
            await self.stop_flow()

        del ThreadSafeCache._instance
        ThreadSafeCache._instance = None
        if self.flow_monitor.active_flow is None:
            self._logger.info("START flow {}".format(kwargs["flow"]))
            # TODO: need to chenage the flow monitor to pass container_conf as a dict
            commands_to_launch = self.flow_monitor.load(flow)
            if len(commands_to_launch) == 0:
                # nothing to launch
                return

            # Clean all Flow Vars
            Var.delete_all(scope="Flow")

            # Lifecycle Nodes will be launched in the beginning, if they are starting nodes
            # they also need to be activated
            ros2_lifecycle_nodes_to_activate = []
            for lc_node in self.flow_monitor.load_ros2_lifecycle():
                if lc_node["node"] not in [command["node"] for command in commands_to_launch]:
                    commands_to_launch.append(lc_node)
                else:
                    ros2_lifecycle_nodes_to_activate.append(lc_node["node"])

            tasks = []
            try:
                for command in commands_to_launch:
                    packages = self.flow_monitor.get_node_packages(command["node"])
                    await self.dump_packages(packages)
                    tasks.append(
                        asyncio.create_task(self.launch_element(wait=False, **command))
                    )

                # wait until all are launched
                await asyncio.gather(*tasks)
            except (SubprocessError, OSError, ValueError, TypeError) as e:
                self._logger.critical(
                    "An error occurred while starting a flow, see errors"
                )
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
        """
        Process command STOP, to stop flow
        Args:
            **kwargs:
                command (str): need to be string with "STOP"
                flow (str): which flow to stop

        Returns: None

        """
        self.reset_emergency_params()
        command = kwargs.get("command", None)
        flow = kwargs.get("flow", None)
        if not all([command, flow]):
            self._logger.error(
                "STOP command failed. Format is {}. Other parameters ignored.".format(
                    self.commands.help("STOP")
                )
            )
            return
        if self.flow_monitor.active_flow is not None:
            self._logger.info("STOP flow {}".format(kwargs["flow"]))
            # asyncio.create_task(self.stop_flow())
            await self.stop_flow()
        else:
            self._logger.error("No flow active. START a flow first.")

    async def process_transition(self, **kwargs):
        """
        Process transition command, to do transition in the flow
        Args:
            **kwargs:
                command (str): need to be "TRANS" string
                node (str): the node that initiated the transition
                port (str): port name that initiated the transition.
                data (str): transition message

        Returns:

        """
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
            self._logger.warning(
                "EMERGENCY button was pressed, Terminating transition!!"
            )
            return

        if not all([command, node, port]):
            self._logger.error(
                "TRANS command failed. Format is {}. Other parameters ignored.".format(
                    self.commands.help("TRANS")
                )
            )
            return
        self._logger.info("TRANS from node: {}   port: {}".format(node, port))
        if self.flow_monitor.active_flow is None:
            self._logger.error("No flow active. START a flow first.")
            return

        commands_to_launch = self.flow_monitor.transition(
            node, port, self.active_states, transition_msg=trans_msg
        )

        if (
            len(set.difference(self.active_states, {node})) + len(commands_to_launch)
            == 0
        ):
            # if after stopping the node, we are left with not state nodes,
            # it's time to die
            return await self.stop_flow()

        all_nodes_to_launch = [command["node"] for command in commands_to_launch]
        nodes_to_kill = [
            node for node in self.nodes_lchd if node not in all_nodes_to_launch
        ]
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
                asyncio.create_task(self.process_kill(node=node_name, command="kill"))
                # node_to_kill.kill())

        tasks = []
        for command in commands_to_launch:
            if command["node"] in nodes_to_launch:
                packages = self.flow_monitor.get_node_packages(command["node"])
                await self.dump_packages(packages)
                # launch element
                tasks.append(
                    asyncio.create_task(self.launch_element(wait=True, **command))
                )

        if type(self).EMERGENCY_FLAG and not self.should_skip_node(node):
            for task in tasks:
                task.cancel()
            return

        await asyncio.gather(*tasks)

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
        Args:
            **kwargs:
                data (dict): data with the name of the lock

        Returns: None

        """

        try:
            data = kwargs.get("data", {})

            self.acq_locks.update({data.get("name"): data})
            asyncio.create_task(Lock.enable_heartbeat(**data))

        except Exception as e:
            self._logger.error(f"Error while processing LOCK command {str(e)}")

    async def process_unlock(self, **kwargs):
        """
        Process command UNLOCK
        This command disables Lock heartbeat for a specific Lock
        Args:
            **kwargs:
                 data (dict): data with the name of the lock to stop the heartbeat.
        Returns: None

        """

        data = kwargs.get("data", {})

        try:
            Lock.disable_heartbeat(**data)

        except Exception as e:
            self._logger.error(f"Error while processing UNLOCK command {str(e)}")

        finally:
            if "name" in data and data["name"] in self.acq_locks:
                self.acq_locks.pop(data["name"])

    async def process_run(self, **kwargs):
        """
        Process command RUN
        It Runs a Node Inst and all its dependencies
        Args:
            **kwargs:
                command (str): has to be "RUN" string
                node (str): the name of the string

        Returns: None

        """
        command = kwargs.get("command", None)
        node = kwargs.get("node", None)
        if not all([command, node]):
            self._logger.error(
                "RUN command failed. Format is {}. Other parameters ignored.".format(
                    self.commands.help("RUN")
                )
            )
            return
        commands_to_launch = self.flow_monitor.get_commands(
            [node], self.flow_monitor.active_flow
        )
        all_nodes_to_launch = [command["node"] for command in commands_to_launch]

        nodes_to_launch = [
            node
            for node in all_nodes_to_launch
            if node not in self.nodes_lchd and node not in self.persistent_nodes_lchd
        ]

        if not nodes_to_launch:
            self._logger.warning(
                "Node {} is already launched or was not found".format(node)
            )
            return

        self._logger.debug(f"RUN node {node}")

        tasks = []
        for command_dict in commands_to_launch:
            if command_dict["node"] in nodes_to_launch:
                tasks.append(
                    asyncio.create_task(self.launch_element(wait=True, **command_dict))
                )
        await asyncio.gather(*tasks)

    async def process_kill(self, **kwargs):
        """
        Process command KILL
        It Kills a Node Inst and all its dependencies (if flag dependencies is true)
        Args:
            **kwargs:
                command (str): has to be "KILL" string
                node (str): the name of the string
        Returns:

        """
        command = kwargs.get("command", None)
        node = kwargs.get("node", None)
        # TODO: option to kill dependencies
        # dependencies = kwargs.get("dependencies", False)

        if not all([command, node]):
            self._logger.error(
                f"KILL command failed. Format is {self.commands.help('KILL')}."
                f"Other parameters ignored."
            )
            return

        self._logger.debug(f"KILL node {node}")

        element = self.nodes_lchd.get(node, None) or self.persistent_nodes_lchd.get(
            node, None
        )

        if element is None:
            self._logger.warning(
                "Could not kill Node {} because is not launched".format(node)
            )
            return

        await element.kill()
        asyncio.create_task(self.clean_element(element, node))

    async def ros2_lifecycle(self, node_name: str, command):
        """Handles ROS2 Lifecycle managed nodes
        create, configure, cleanup, activate, deactivate, shutdown, destroy
        """
        self._logger.info(
            f"Spawner: ROS2 Lifecycle command: {command} on node:{node_name}"
        )
        _stdout = None
        await asyncio.create_subprocess_exec(
            *command, stdin=None, stdout=_stdout, env=ENVIRON_ROS2
        )

    async def dump_packages(self, packages: dict):
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
                                asyncio.get_running_loop().run_in_executor(
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
                    self._logger.critical(
                        msg_invalid_checksum.format(checksum, file_name)
                    )

    async def process_emergency_set(self, **kwargs):
        """
        activates EMERGENCY button pressed, all active states will be killed unless it matches
        a specific pattern provided in data in kwargs
        Args:
            **kwargs:
                data (dict): a dict with nodes to skip

        Returns: None

        """
        data = kwargs.get("data", {})
        self._logger.info("EMERGENCY BUTTON PRESSED, SET EMERGENCY_FLAG = True")
        type(self).EMERGENCY_FLAG = True

        for regex_str in data.get("nodes_to_skip", []):
            if len(regex_str) == 0:
                continue
            self.nodes_to_skip.append(re.compile(regex_str))

        tasks = []
        for node_name in self.active_states:
            if self.should_skip_node(node_name):
                continue
            kwargs_local = {"command": "KILL", "node": node_name}
            tasks.append(asyncio.create_task(self.process_kill(**kwargs_local)))

        # wait for all get_keys tasks to run
        await asyncio.gather(*tasks)

    async def process_emergency_unset(self, _):
        """
        deactivate EMERGENCY button, unsetting relevant flags
        Args:
            _: unused args

        Returns: None

        """
        self.reset_emergency_params()
