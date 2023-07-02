"""
   Copyright (C) Mov.ai  - All Rights Reserved
   Unauthorized copying of this file, via any medium is strictly prohibited
   Proprietary and confidential

   Developers:
   - Manuel Silva (manuel.silva@mov.ai) - 2020
   - Tiago Paulino (tiago@mov.ai) - 2020
"""
import re
import copy
import rosparam
from types import SimpleNamespace
import os

from movai_core_shared.consts import (
    ROS1_NODELET,
    ROS1_NODE,
    ROS1_PLUGIN,
    MOVAI_STATE,
    ROS1_ACTIONSERVER,
    ROS1_ACTIONCLIENT,
    MOVAI_NODE,
    MOVAI_SERVER,
    ROS2_NODE,
    ROS2_LIFECYCLENODE,
    LINK_REGEX,
)

from movai_core_shared.envvars import (
    ENVIRON_ROS1,
    ENVIRON_ROS2,
    ENVIRON_GDNODE,
    ROS1_LIB,
    ROS1_NODELET_CMD,
    ROS2_LIB,
    APP_PATH,
    ROS1_USER_WS,
)

from movai_core_shared.logger import Log

from dal.models.scopestree import scopes
from dal.helpers.parsers import ParamParser
from dal.new_models import Flow


LOGGER = Log.get_logger("spawner.mov.ai")


class FlowMonitor:
    def __init__(self):
        self.active_flow = None
        self.active_dependencies = None
        self.cache_commands = {}
        self.dependencies = []
        self.ros_types = [ROS1_NODE, ROS1_NODELET]
        # self.ros_types = [ROS1_NODELET, ROS1_NODE, ROS1_PLUGIN]
        self.param_parser = None
        self.cached_remaps = {}

    def load(self, flow_name: str) -> list:
        """Load a specific flow, returns starting commands"""
        LOGGER.info(("load flow {}".format(flow_name)))

        try:
            # unload previous loaded flow
            self.unload()

            new_flow = Flow(flow_name)
            nodes_to_start = new_flow.get_start_nodes()
            if len(nodes_to_start) == 0:
                # no start link
                raise ValueError("No start links found")

            self.active_flow = new_flow
            self.param_parser = ParamParser(self.active_flow)

            # list of tuples with (node_name, command, is_persistent)
            commands_to_launch = self.get_commands(nodes_to_start, new_flow)

            return commands_to_launch

        except Exception as err:
            LOGGER.error(str(err))
            LOGGER.error(repr(err))
            self.unload()
            return []

    def unload(self) -> None:
        """Unload flow"""
        self.cache_commands = {}
        self.cached_remaps = {}
        if self.active_flow:
            dependencies_down = copy.deepcopy(self.active_dependencies)
            for dependency in self.dependencies:
                if dependency in dependencies_down:
                    dependencies_down.remove(dependency)

            # unload data from memory
            #self.active_flow.get_first_parent("workspace").unload_all()
            self.active_flow = None

    def transition(
        self,
        node_name: str,
        port_name: str,
        active_states: set = None,
        transition_msg=None,
    ) -> list:
        """ "Get commands for the transition"""

        try:
            nodes_to_transit = self.active_flow.get_node_transitions(node_name, port_name)

            for state in active_states or set():
                if state != node_name:
                    nodes_to_transit.add(state)

            LOGGER.debug(f"Node(s) to transit: {nodes_to_transit}")

            return self.get_commands(
                nodes_to_transit, self.active_flow, transition_msg=transition_msg
            )

        except Exception as e:
            LOGGER.error(e)
            return []

    def load_ros2_lifecycle(self) -> list:
        """Returns all lifecycle ros2 nodes (they will start as unconfigured)"""
        commands_to_launch = []
        for lc_node in self.active_flow.get_lifecycle_nodes():
            if lc_node not in [name[0] for name in commands_to_launch]:
                commands_to_launch.append(
                    (
                        lc_node,
                        self.get_node_cmd(lc_node, self.active_flow),
                        self.active_flow.full.NodeInst[lc_node].is_persistent,
                        False,
                        self.get_node_EnvVars(lc_node, self.active_flow),
                    )
                )
        return commands_to_launch

    def get_commands(self, nodes: list, flow: Flow, transition_msg=None) -> list:
        """Get commands to launch nodes"""
        commands_to_launch = []
        for node_name in nodes:

            try:
                node_inst = flow.full.NodeInst[node_name]
                for node_dependency in flow.get_node_dependencies(node_name):
                    node_command = self.cache_commands.get(node_dependency, None)
                    node_dep_inst = flow.full.NodeInst[node_dependency]
                    if node_command:
                        if node_command not in commands_to_launch:
                            commands_to_launch.append(node_command)
                    elif node_command is None:
                        cmd = self.get_node_cmd(node_dependency, flow)
                        is_state = node_dep_inst.node_template.Type == MOVAI_STATE
                        # do not launch dummy nodes or plugins
                        if (
                            not node_dep_inst.is_dummy
                            and not node_dep_inst.node_template.Type == ROS1_PLUGIN
                            and node_dep_inst.is_node_to_launch
                        ):
                            to_launch = (
                                node_dependency,
                                cmd,
                                node_dep_inst.is_persistent,
                                is_state,
                                self.get_node_EnvVars(node_dependency, flow),
                            )
                            if to_launch not in commands_to_launch:
                                commands_to_launch.append(to_launch)
                                self.cache_commands[node_dependency] = to_launch
                        else:
                            self.cache_commands[node_dependency] = False
                cmd = self.get_node_cmd(node_name, flow, transition_msg)
                # tuple(node_name, command, is_persistent, is_state)
                is_state = node_inst.node_template.Type == MOVAI_STATE
                commands_to_launch.append(
                    (
                        node_name,
                        cmd,
                        node_inst.is_persistent,
                        is_state,
                        self.get_node_EnvVars(node_name, flow),
                    )
                )
            except Exception as e:
                LOGGER.error(e)

        return commands_to_launch

    def get_node_remaps(self, flow: Flow, node_name: str = None) -> dict:
        """
        output: {"Node_Inst": {"port_name": "remap", ...}, ...}
           or
        output_str: "node_name port_name1:=remap1 ... port_nameN:=remapN"
        """
        remaps = flow.remaps
        output = {}
        node_inst = None
        if flow.name in self.cached_remaps:
            output = self.cached_remaps[flow.name]
        else:
            for remap in remaps:
                to_ports = remaps[remap]["To"]
                from_ports = remaps[remap]["From"]

                for port in to_ports + from_ports:
                    p = re.search(LINK_REGEX, port)
                    if p is not None:
                        node_inst, _, port_inst, _, port_name = p.groups()
                    else:
                        raise ValueError(
                            "ValueError: Link in Flow should be in format"
                            '"Node_inst/Port_inst/Port_name"'
                        )
                    if node_inst not in output:
                        output[node_inst] = {}
                    output[node_inst][port] = remap
            self.cached_remaps[flow.name] = output
        if node_name is not None:
            if node_name in output:
                # flow.get_node_type(node_name)
                node_type = flow.full.NodeInst[node_name].node_template.Type
                output_list = []
                for port_remap, value in output[node_name].items():
                    # skip start or end links
                    links_to_skip = ["START", "END"]
                    if any(
                        list(
                            map(
                                lambda x: x in port_remap.split("/")[-1].upper()
                                or x in value.split("/")[-1].upper(),
                                links_to_skip,
                            )
                        )
                    ):
                        continue

                    # Lets analyse the value (right side) -> if "~" in port_inst replace by node_inst/
                    temp_value = re.search(LINK_REGEX, value)
                    if temp_value is not None:
                        node_inst, _, port_inst, _, port_name = temp_value.groups()
                        if port_inst.startswith("~"):
                            port_inst = port_inst.replace("~", node_inst + "/", 1)
                            # rebuild the value with the change
                            value = "%s/%s/%s" % (node_inst, port_inst, port_name)
                    # when the link is in the wrong format (only middle part)
                    else:
                        if node_inst is None:
                            node_inst = list(output.keys())[-1]
                        value = value.replace("~", node_inst + "/", 1)

                    if node_type in [
                        ROS1_NODE,
                        ROS1_NODELET,
                        ROS2_NODE,
                        ROS2_LIFECYCLENODE,
                    ]:
                        actionlib_types = [ROS1_ACTIONSERVER, ROS1_ACTIONCLIENT]
                        p = re.findall(LINK_REGEX, port_remap)
                        node_inst, _, port_inst, _, port_name = p[0]
                        # flow.get_node(node_name)['PortsInst'][port_inst]['Template'] in actionlib_types:
                        if (
                            flow.full.NodeInst[node_name]
                            .node_template.PortsInst[port_inst]
                            .Template
                            in actionlib_types
                        ):
                            output_list.append("%s/%s:=%s" % (port_inst, port_name, value))
                        else:
                            output_list.append("%s:=%s" % (port_inst, value))
                    else:
                        output_list.append("%s:=%s" % (port_remap, value))

                # If we want to remove useless remaps
                # output_list = [elem for elem in output_list if elem.split(':=')[0]!=elem.split(':=')[1]]
                return output_list
            return []
        return output

    def get_node_Parameters(self, node_name: str, flow: Flow, check_plugins: bool = True) -> list:
        """Return node parameters based on type"""
        output = []
        node_type = flow.full.NodeInst[node_name].node_template.Type

        if check_plugins:
            # check if node has plugins linked
            node_plugins = flow.get_node_plugins(node_name)
            for plugin in node_plugins:
                plugin_inst = flow.full.NodeInst[plugin]
                params = flow.get_node_params(plugin)
                plugin_path = plugin_inst.node_template.Path
                # Remove None parameters
                for key, value in list(params.items()):
                    if value is None:
                        del params[key]
                rosparam.upload_params("/%s/%s" % (node_name, plugin_path), params, False)

        params = flow.get_node_params(node_name)
        if node_type in self.ros_types:
            # Remove None parameters
            for key, value in list(params.items()):
                if value is None:
                    del params[key]
            namespace = params.get("__ns")
            if namespace:
                rosparam.upload_params("/%s/%s" % (namespace, node_name), params, False)
                output = ["__ns:=%s" % namespace]
            else:
                rosparam.upload_params("/%s" % node_name, params, False)
        else:
            params = ["%s:=%s" % (key, value) for key, value in params.items()]

            if params and node_type not in self.ros_types:
                output = ["-p", '"%s"' % ";".join(params)]

        return output

    def get_node_EnvVars(self, node_name: str, flow: Flow) -> dict:
        """Return node environment variables"""
        node_inst = flow.full.NodeInst[node_name]
        params = node_inst.node_template.EnvVar
        node_type = node_inst.node_template.Type
        output = {}

        node_type = node_inst.node_template.Type

        n_types = {
            ROS2_NODE: ENVIRON_ROS2,
            ROS2_LIFECYCLENODE: ENVIRON_ROS2,
            MOVAI_NODE: ENVIRON_GDNODE,
            MOVAI_STATE: ENVIRON_GDNODE,
            MOVAI_SERVER: ENVIRON_GDNODE,
        }

        output.update(n_types.get(node_type, ENVIRON_ROS1))

        # wait for implementation details
        for param, value in params.items():
            output.update({param: value.Value})

        return output

    def get_node_CmdLines(self, node_name: str, flow: Flow) -> list:
        """Return node CmdLines"""
        node_inst = flow.full.NodeInst[node_name]
        params = [
            self.param_parser.parse(
                key,
                (node_inst.CmdLine.get(key) or SimpleNamespace(Value=value.Value)).Value,
                node_name,
                node_inst,
                flow.ref,
            )
            for key, value in node_inst.node_template.CmdLine.items()
        ]

        output = []

        if node_inst.node_template.Type == ROS1_NODELET:
            nodelet_manager_name = flow.get_nodelet_manager(node_name)
            if nodelet_manager_name:
                output.append("load")
                output.append(node_inst.node_template.Path)
                output.append(nodelet_manager_name)
            else:
                output.append("manager")

        for param in params:
            output.extend(param.split(" "))

        return output

    def get_node_packages(self, node_name: str) -> dict:
        """Return node packages"""
        if self.active_flow is None:
            raise Exception("No flow active.")
        return self.get_template_packages(node_name, self.active_flow)

    def get_lifecycle_nodes(self) -> list:
        """Returns list of all nodes with lifecycle in the current active flow"""
        if self.active_flow is None:
            raise Exception("No flow active.")
        return self.active_flow.get_lifecycle_nodes()

    def get_node_type(self, node_name: str) -> str:
        """Return node type"""
        if self.active_flow is None:
            raise Exception("No flow active.")
        # .get_node_type(node_name)
        return self.active_flow.full.NodeInst[node_name].node_template.Type

    def get_template_packages(self, node_name: str, flow: Flow) -> dict:
        """Return node template packages"""
        output = []  # [{"name": package_name, "file": package_file, "path": package_path}]

        node_template = flow.full.NodeInst[node_name].node_template
        packages = node_template.PackageDepends

        if packages:
            for package in packages:
                plist = package.split("/")
                package_name = plist[0]
                package_file = ""
                if len(plist) > 1:
                    package_file = plist[-1]
                    package_path = "/".join(plist[:-1])
                else:
                    package_path = plist[0]
                output.append(
                    {
                        "package": package_name,
                        "file": package_file,
                        "path": package_path,
                    }
                )
        return output

    def get_node_template_name(self, node_name: str, flow: Flow) -> str:
        """Return node instance template name"""
        return flow.full.NodeInst[node_name].Template

    def get_node_type_cmd(self, node_name: str, flow: Flow) -> list:
        """Get executable to launch the node based on type"""
        node_template = flow.full.NodeInst[node_name].node_template
        node_type = node_template.Type
        if node_type in self.ros_types:
            if node_type == ROS1_NODELET:
                output = [ROS1_NODELET_CMD]
            else:
                path = node_template.Path
                if "/opt/" in path:
                    output = [path]
                else:
                    dev_path = "".join([ROS1_USER_WS, "/lib", path])
                    if os.path.exists(dev_path) is False:
                        output = ["".join([ROS1_LIB, path])]
                    else:
                        output = [dev_path]
        elif node_type in [ROS2_NODE, ROS2_LIFECYCLENODE]:
            path = node_template.Path
            if "/opt/" in path:
                output = [path]
            else:
                output = ["".join([ROS2_LIB, path])]

        elif node_type == ROS1_PLUGIN:
            output = []
        else:
            output = ["gd_node"]
        return output

    def get_node_cmd(self, node_name: str, flow: Flow, transition_msg=None) -> list:
        """Return complete command to launch the node"""
        cmd = []

        node_inst = flow.full.NodeInst[node_name]
        node_template_name = node_inst.Template
        node_type = node_inst.node_template.Type

        cmd.extend(self.get_node_type_cmd(node_name, flow))

        if node_type in self.ros_types:
            cmd.append("__name:=%s" % node_name)
        else:
            cmd.extend(["-i", "%s" % node_name])
            cmd.extend(["-n", "%s" % node_template_name])
            cmd.extend(["-f", "%s" % flow.Label])
            # TODO use envvar to check if in development mode
            cmd.extend(["-d"])

            if node_type == MOVAI_STATE:
                cmd.extend(["-m", "%s" % transition_msg])

        cmd.extend(self.get_node_Parameters(node_name, flow))

        # cmd.extend(self.get_node_EnvVars(node_name, flow))

        cmd.extend(self.get_node_CmdLines(node_name, flow))

        cmd.extend(self.get_node_remaps(flow, node_name))

        return cmd
