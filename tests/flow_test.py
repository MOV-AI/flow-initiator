"""
   Copyright (C) Mov.ai  - All Rights Reserved
   Unauthorized copying of this file, via any medium is strictly prohibited
   Proprietary and confidential

   Developers:
   - Manuel Silva  (manuel.silva@mov.ai) - 2020
   - Dor Marcous   (Dor@mov.ai) - 2021
"""

import unittest
import os
from deepdiff import DeepDiff

from dal.scopes import Flow
from dal.scopes import scopes

from dal.models import Node

os.environ["DEVICE_NAME"] = "robot"


class TestFlow(unittest.TestCase):
    """
    Test flow refactor
    """

    def test_get_dict(self):
        """
        Test get_dict
        """
        flow_name = "ign_sim_demo"

        # flow instance using deprecated api
        flow_deprec = Flow(flow_name)

        # flow instance using the current api
        flow_curr = scopes().Flow[flow_name]

        dict_a = flow_deprec.get_dict(recursive=True)
        dict_b = flow_curr.get_dict()

        with self.subTest():
            id_links_a = list(dict_a["Flow"][flow_name]["Links"].keys())
            id_links_b = list(dict_b.Links.keys())

            self.assertCountEqual(id_links_a, id_links_b)

        with self.subTest():
            id_nodeinst_a = list(dict_a["Flow"][flow_name]["NodeInst"].keys())
            id_nodeinst_b = list(dict_b.NodeInst.keys())

            self.assertCountEqual(id_nodeinst_a, id_nodeinst_b)

    def test_get_node(self):
        """
        flow.get_node should return an instance of Node
        """
        flow_name = "ign_sim_demo"
        node_instance_name = "center"

        flow = scopes().Flow[flow_name]
        node = flow.get_node(node_instance_name)

        self.assertIsInstance(node, Node)

    def test_get_start_nodes(self):
        """
        flow.get_start_nodes shoudl return a list of
        nodes linked with the StARt block
        """
        flow_name = "ign_sim_demo"

        expected = ['tugbot_sim__init', 'tugbot_sim__init']

        flow = scopes().Flow[flow_name]
        start_nodes = flow.get_start_nodes()

        self.assertCountEqual(start_nodes, expected)

    def test_compare_remaps(self):
        """
        Compare remaps obtained from deprecated api with new api
        """
        flow_name = "mapping"

        # calc remaps using the deprecated api
        flow_deprec = Flow(flow_name)
        remaps_deprec = flow_deprec.calc_remaps()

        # calc remaps using the current api
        flow_curr = scopes().Flow[flow_name]
        remaps_curr = flow_curr.remaps

        result = DeepDiff(
            remaps_curr, remaps_deprec, ignore_order=True)

        self.assertDictEqual(result, {})

    def test_get_node_transitions(self):
        """
        Should return a list of nodes to transit to
        """

        flow_name = "mapping"
        node_inst_name = "mapping_main"
        expected = {"wait_save", "trigger_map_saver"}

        flow = scopes().Flow[flow_name]
        result = flow.get_node_transitions(node_inst_name)
        print(result)

        self.assertEqual(result, expected)

    def test_get_nodelet_manager(self):
        """
        Should return the name of the nodelet manager
        """

        flow_name = "realsense2_camera"
        node_inst_name = "camera"
        expected = "manager"

        flow = scopes().Flow[flow_name]
        result = flow.get_nodelet_manager(node_inst_name)

        self.assertEqual(result, expected)

    def test_get_node_dependencies(self):
        """
        Should return a list of node dependencies
        """

        flow_name = "ign_sim_demo"
        node_inst_name = "tugbot_sim__gripper_sim"
        expected = ["tugbot_sim__drivers"]

        flow = scopes().Flow[flow_name]
        result = flow.get_node_dependencies(node_inst_name)

        self.assertEqual(result, expected)

    def test_get_node_plugins(self):
        """
        Should return a list of node plugins
        """

        flow_name = "tugbot_navigation"
        node_inst_name = "move_base"
        expected = ['global_costmap', 'local_costmap', 'movai_global_planner', 'teb_planner']

        flow = scopes().Flow[flow_name]
        result = flow.get_node_plugins(node_inst_name)

        self.assertCountEqual(result, expected)

    def test_get_node_inst_param1(self):
        """
        Should return the node instance parameter correctly parsed
        """

        flow_name = "mapping"
        node_inst_name = "drivers__central_controller"
        param_name = "_namespace"
        expected = "central_controller"

        result = scopes().Flow[flow_name].get_node_inst(
            node_inst_name).get_param(param_name)

        self.assertEqual(result, expected)

    def test_get_node_inst_param2(self):
        """
        Should return the node instance parameter correctly parsed
        """

        flow_name = "movai_lab"
        node_inst_name = "tugbot__drivers__camera_back__camera"

        flow = scopes().Flow[flow_name]

        with self.subTest():
            # evaluating
            # serial_no: $(config ${DEVICE_NAME}.$(param _tf_prefix).serial_no)
            #  - same as $(config robot.camera_back.serial_no)
            # _tf_prefix: $($flow camera)  - from node instance camera
            # ${DEVICE_NAME} is an env var
            #
            param_name = "serial_no"
            expected = "944122072319"

            result = flow.get_node_inst_param(node_inst_name, param_name)

            self.assertEqual(result, expected)

        with self.subTest():
            param_name = "_tf_prefix"
            expected = "camera_back"

            result = flow.get_node_inst_param(node_inst_name, param_name)

            self.assertEqual(result, expected)

    def test_get_node_inst_params(self):
        """
        Should return the node instance parameter correctly parsed
        from get_node_params
        """

        flow_name = "movai_lab"
        node_inst_name = "tugbot__drivers__camera_back__camera"
        param_name = "serial_no"
        expected = "944122072319"

        flow = scopes().Flow[flow_name]

        with self.subTest():
            result = flow.get_node_params(node_inst_name)[param_name]

        self.assertEqual(result, expected)

    def test_node_inst_does_not_exist(self):
        """
        Should raise a KeyError exception as the node does not
        exist in the flow
        """

        flow_name = "movai_lab"

        flow = scopes().Flow[flow_name]

        with self.assertRaises(KeyError):
            flow.get_node_inst("noname")


if __name__ == '__main__':
    unittest.main()
