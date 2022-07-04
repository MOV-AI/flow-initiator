"""
A file to manager virtual network_name
"""
import threading

from docker.api.container import ContainerApiMixin
from docker.models.containers import Container
from docker.models.networks import Network
from docker.errors import NotFound
from typing import Optional, Union
from . import DockerBaseManager, check_dockerd
from movai_core_shared.logger import Log

log = Log.get_logger("NetworkManager")


class NetworkManager(DockerBaseManager):
    """
    A class to manage virtual networks
    """

    NETWORK_PREFIX = "MovaiNetwork"

    def __init__(self, default_labels=None):
        super().__init__(default_labels)

    @check_dockerd
    def create_network(self, name: str, labels: Optional[dict] = None) -> Network:
        """
        Create new docker network_name
        Args:
            name: The network_name container_name
            labels: labels for the network_name
        Returns:
            The new network object.
        """
        if threading.current_thread() != threading.main_thread():
            log.info(f"Creating new network {name}")
        network_labels = {}
        network_labels.update(self._default_labels)
        if labels is not None:
            network_labels.update(labels)

        networks = self.remove_duplicate_network(name)
        if name not in networks:
            networks[name] = self._docker_client.networks.create(
                name=name, internal=False, labels=network_labels
            )
        else:
            log.warning(f"Can't create network {name}, already exists")
        return networks[name]

    def remove_network(self, network_id: str):
        """removes network from docker networks.

        Args:
            network_id (str): network id that need to be removed.
        """
        network_obj = self.get_network(network_id)
        if network_obj is None and self.NETWORK_PREFIX not in network_id:
            network_obj = self.get_network(f"{self.NETWORK_PREFIX}-{network_id}")
        if network_obj is None:
            log.warning(f"Can't remove network: {network_id}, doesn't exist")
            return
        for container in network_obj.containers:
            log.warning(
                f"disconnecting container {container.short_id} from network {network_obj.short_id}"
            )
            network_obj.disconnect(container)
        network_obj.remove()
        log.info(f"network {network_obj.name} removed !, id={network_id}")

    def remove_duplicate_network(self, name):
        """Remove duplicated network with the same name
        Args:
            name: The name of the wanted

        Returns:
            A update dictionary with the networks

        """
        _networks = {}
        for network_obj in self._docker_client.networks.list():
            if (
                network_obj.name in _networks
                and network_obj.name.find(self.NETWORK_PREFIX) != -1
            ):
                log.warning(
                    f"found duplicated Movai Networks names: "
                    f"{network_obj.name}, {network_obj.short_id} and {_networks[name]}"
                )
                self.remove_network(network_obj.short_id)
                self.remove_network(_networks[name])
                del _networks[name]
            else:
                _networks[network_obj.name] = network_obj.short_id
        return _networks

    def get_or_create_network(
        self, name: str, labels: Optional[dict] = None
    ) -> Network:
        """
        Get existing network_name otherwise create new one
           Args:
               name: the network_name container_name
               labels: labels for the network_name
           Returns:
               The new/existing network_name
        """
        if threading.current_thread() != threading.main_thread():
            log.debug(f"Trying to get network: {name}")
        network = self.get_network(name)
        if network is None:
            network = self.create_network(name, labels)
        return network

    @check_dockerd
    def get_network(self, name: str) -> Optional[Network]:
        """
        Get a network_name by container_name
        Args:
            name: container_name of the network_name
        Returns: Network or None if not found
        """
        if threading.current_thread() != threading.main_thread():
            log.debug(f"Getting network: {name}")
        try:
            return self._docker_client.networks.get(name)
        except NotFound:
            return None

    @check_dockerd
    def attach_container_to_network(
        self, container: Union[str, Container], network_name: str, *args, **kwargs
    ):
        """
        Connect a container to this network.

        Args:
            network_name: The network container_name
            container (str): Container to connect to this network, as either
                an ID, container_name, or :py:class:`~docker.models.containers.Container`
                object.
            aliases (:py:class:`list`): A list of aliases for this endpoint.
                Names in that list can be used within the network to reach the
                container. Defaults to ``None``.
            links (:py:class:`list`): A list of links for this endpoint.
                Containers declared in this list will be linked to this
                container. Defaults to ``None``.
            ipv4_address (str): The IP address of this container on the
                network, using the IPv4 protocol. Defaults to ``None``.
            ipv6_address (str): The IP address of this container on the
                network, using the IPv6 protocol. Defaults to ``None``.
            link_local_ips (:py:class:`list`): A list of link-local (IPv4/IPv6)
                addresses.
            driver_opt (dict): A dictionary of options to provide to the
                network driver. Defaults to ``None``.

        """
        log.debug(f"Attaching container: {container} to network: {network_name}")
        network = self.get_or_create_network(network_name)
        containers = network.containers
        if isinstance(container, str):
            containers = [container.name for container in containers]
        if container in containers:
            log.info(f"container: {container} already in network: {network.name}")
            return
        network.connect(container, *args, **kwargs)

    def create_network_config(self, endpoints_config: dict) -> dict:
        """A wrapper for container tool"""
        log.debug("creating new network configuration")
        return self._docker_APIClient.create_networking_config(endpoints_config)

    create_network_config.__doc__ += ContainerApiMixin.create_networking_config.__doc__

    def create_endpoint_config(self, *args, **kwargs) -> dict:
        """A wrapper for container tool"""
        log.debug("creating new endpoint configuration")
        return self._docker_APIClient.create_endpoint_config(*args, **kwargs)

    create_endpoint_config.__doc__ += ContainerApiMixin.create_endpoint_config.__doc__
