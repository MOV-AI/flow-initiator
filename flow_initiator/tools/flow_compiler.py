#!/usr/bin/env python3
#
# a flow compiler
#


import sys
import json

from collections import namedtuple

from dal.models.scopestree import scopes
from movai_core_shared.consts import MOVAI_STATE
from dal.new_models import Node as NewNode

# typing
Flow = Node = None
scopes_root = scopes()
Flows = scopes().Flow  # pylint: disable=invalid-name

Nodes = scopes().Node  # pylint: disable=invalid-name

FlowCompiled = namedtuple("FlowCompiled", ("flow", "graph", "start"))


def flatten(flow: Flow, prefix: str = ""):
    """Flatten a flow, return a dictionary with
    the nodes and the links of the flow and its subflows

    nodes are {nodeinst_label: nodeinst, ...}
    links are [{from: f, to: t, ...}, ...]
    """
    # nodes have names
    nodes = {}
    # links are just dicts (From, To), list of dicts
    links = []

    # sub flows
    for iflow_name in flow.Container:
        iflow_dict = flow.Container[iflow_name]
        iflow = Flows[iflow_dict.ContainerFlow]
        iflattened = flatten(iflow, f"{prefix}{iflow_dict.ContainerLabel}__")
        nodes.update(iflattened["nodes"])
        links.extend(iflattened["links"])

    # this flow nodes
    nodes.update(
        {
            f"{prefix}{flow.NodeInst[node_name].NodeLabel}": flow.NodeInst[node_name]
            for node_name in flow.NodeInst
        }
    )
    # and the links, prefix `From` and `To`, keep the rest as it is
    for link in flow.Links.values():
        # prefix From and To
        new_link = {"From": f'{prefix}{link["From"]}', "To": f'{prefix}{link["To"]}'}
        # keep the rest untouched
        new_link.update({k: link[k] for k in link if k not in ("From", "To")})
        links.append(new_link)

    return {"nodes": nodes, "links": links}


def _resolve_deps(graph, nodes, deps_set, node: str):
    # add self
    deps_set.add(node)

    # add dependencies
    node_set = graph.get(node, set())
    for next_node_name in node_set:
        if next_node_name in deps_set:
            # already went that way
            continue
        # next_node_temp = Nodes[nodes[next_node_name].Template]
        next_node_temp = NewNode(next_node_name)
        if next_node_temp.Type == MOVAI_STATE:
            # not getting into that
            continue
        # recursively
        _resolve_deps(graph, nodes, deps_set, next_node_name)


def flow_compile(flow: Flow) -> FlowCompiled:
    """Compile a flow
    return the "flattened" flow, the dependency graph and a list of starting nodes

    flattened flow is a dict containing all the nodeinst and links of all the flow and subflows
    as a dict:
        {'nodes': {nodelabel: <nodeinst>, ...}, 'links': [{'From': from, 'To': to}, ...]},
    the dependency graph is a map os sets {nodelabel: set(deps), ...}
    the starting nodes is a list of strings, with the names of the node instances
    """

    # flattenewd
    fl_flow = flatten(flow)
    nodes = fl_flow["nodes"]
    links = fl_flow["links"]
    starting_nodes = set()

    graph = dict()

    for link_dict in links:

        l_from, l_to = link_dict["From"], link_dict["To"]
        l_dep = link_dict.get("Dependency", 0) ^ 3  # reverse its usage
        n_from = l_from.split("/", 1)[0]
        n_to = l_to.split("/", 1)[0]

        # if n_from.lower() in ('start', 'end') or n_to.lower() in ('start', 'end'):
        #     # nope
        #     continue

        if n_from.lower() == "start":
            starting_nodes.add(n_to)
            continue
        if n_to.lower() == "end":
            continue

        # l_dep, reversed, bit mask
        # 0: no dependencies
        # 1: to -> from (`to` depends on `from`)
        # 2: from -> to (`from` depends on `to`)
        # 3: both

        if l_dep & 1:  # to -> from
            graph[n_to] = graph.get(n_to, set())
            graph[n_to].add(n_from)
        if l_dep & 2:  # from -> to
            graph[n_from] = graph.get(n_from, set())
            graph[n_from].add(n_to)

    # now should "resolve" all dependencies,
    # to only movai nodes being "keys"

    # clean the graph, set keys as only movai states and make
    # states not dependant on other states
    sane_graph = {}
    for node_name in graph:
        template = NewNode(node_name)
        if template.Type != MOVAI_STATE:
            continue
        sane_graph[node_name] = set()
        _resolve_deps(graph, nodes, sane_graph[node_name], node_name)

    return FlowCompiled(fl_flow, sane_graph, starting_nodes)


def main():
    """flow compiler CLI entrypoint"""
    try:
        flow_name = sys.argv[1]
    except KeyError:
        print(f"{sys.argv[0]} <flow_name>")
        return 1

    flow = Flows[flow_name]

    compiled = flow_compile(flow)
    # make lists out of the sets
    a_graph = {k: list(compiled.graph[k]) for k in compiled.graph}

    # print it
    # ScopeObjectNode is not JSON serializable -> default
    json.dump(
        {"flow": compiled.flow, "graph": a_graph, "start": list(compiled.start)},
        sys.stdout,
        default=lambda o: o.serialize(),
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
