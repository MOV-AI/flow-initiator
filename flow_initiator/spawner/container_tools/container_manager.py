"""
A file to manage containers
"""
import os
from typing import Optional, Union, List

from docker.api.container import ContainerApiMixin
from docker.types import Mount
from docker.models.containers import Container, ContainerCollection
from docker.errors import NotFound
from . import DockerBaseManager, check_dockerd
from flow_initiator.spawner.exceptions import OrchestratorException
from movai_core_shared.logger import Log

log = Log.get_logger("ContainerManager")


class ContainerManager(DockerBaseManager):
    """
    A class to manage containers.
    """

    LOOPBACK_IP = "127.0.0.1"

    def __init__(self, default_labels=None):
        super().__init__(default_labels)

    @check_dockerd
    def get_container(self, container: str) -> Optional[Container]:
        """
        Get container by name
        Args:
            container: Container name or ID.

        Returns:
            Container if found, otherwise None

        """
        log.debug(f"Trying to get container name: {container}")
        try:
            return self._docker_client.containers.get(container)
        except NotFound:
            log.warning(f"Container {container} not found!")
            return None

    def get_container_state(self, container: str):
        """
        Return the container status from docker inspect
        Args:
            container: Container name or ID.

        Returns: dict of the status

        """
        container = self.get_container(container)
        if container is None:
            return None
        return container.attrs["State"]

    @check_dockerd
    def container_execute_command(self, container_name: str, cmd: str, **kwargs):
        """
        Run new process in a running container.
        Args:
            container_name: name of the container
            cmd: command to execute

        Returns:
            (ExecResult): A tuple of (exit_code, output)
                exit_code: (int):
                    Exit code for the executed command or ``None`` if
                    either ``stream`` or ``socket`` is ``True``.
                output: (generator, bytes, or tuple):
                    If ``stream=True``, a generator yielding response chunks.
                    If ``socket=True``, a socket object for the connection.
                    If ``demux=True``, a tuple of two bytes: stdout and stderr.
                    A bytestring containing response data otherwise.

        """
        log.info(f"In container: {container_name}, executing command: {cmd}")
        container = self.get_container(container_name)
        if container is None:
            log.error(f"Container {container_name} not found!")
            return None
        elif container.status != "running":
            log.error(f"Container {container_name} is not running")
            return None
        return container.exec_run(cmd, **kwargs)

    @check_dockerd
    def stop_container(self, container_name: str, remove: bool = False):
        """
        Stop running a container
        Args:
            remove: if to remove container after stopping
            container_name: name of the container

        """
        log.info(f"Stopping container: {container_name}")
        container = self.get_container(container_name)
        if container is None:
            log.warning(f"Can't remove container {container_name}, not found")
            return
        container.stop()
        if remove:
            self.remove_container(container_name)

    @check_dockerd
    def remove_container(self, container: Union[str, Container], **kwargs):
        """
        Remove this container. Similar to the ``docker rm`` command.

         Args:
             container: name of the container or a container object
             v (bool): Remove the volumes associated with the container
             link (bool): Remove the specified link and not the underlying
                 container
             force (bool): Force the removal of a running container (uses
                 ``SIGKILL``)

        """
        if isinstance(container, str):
            container = self.get_container(container)
        if container is None:
            log.error("can not remove container because container was not found")
            return
        log.warning(f"removing container {container.name}")
        container.remove(**kwargs)

    def run_container(
        self,
        container_name: str,
        hostname: str,
        image: str,
        command: str = None,
        auto_remove: bool = False,
        labels: Optional[dict] = None,
        mounts: Optional[list] = None,
        env: Optional[list] = None,
        volumes: Optional[dict] = None,
        privileged: bool = False,
        devices: Optional[list] = None,
        network_mode: str = "bridge",
        extra_hosts: dict = None,
        capabilities: list = None,
        init: bool = False,
        detach: bool = False,
        **kwargs,
    ):
        """
        Start a new container.
        Args:
            container_name: the name of the container
            hostname: alias configuration for the container network
            image: image name for the container
            init (bool): Run an init inside the container that forwards
            command: optional command to run the container
            detach (bool): Run container in the background
            auto_remove (bool): if to remove the container, when it's stopped.
            labels: label for the container
            mounts: mounts drive option
            env: environment variables for the container
            volumes: volumes to load
            privileged (bool): if to run container in privileged mode
            devices: devices to give permission
            network_mode: type of network mode, default "bridge"
            extra_hosts: extra hosts ips to connect the container
            capabilities: grant capabilities for the container

        Returns:

        """
        log.info(f"Running container {container_name}")
        mounts = list() if mounts is None else mounts
        volumes = dict() if volumes is None else volumes
        extra_hosts = dict() if extra_hosts is None else extra_hosts
        env = list() if env is None else env
        devices = list() if devices is None else devices
        capabilities = list() if capabilities is None else capabilities
        container_labels = {}
        container_labels.update(self._default_labels)
        if labels is not None:
            container_labels.update(labels)
        return self._docker_client.containers.run(
            image=image,
            name=container_name,
            labels=container_labels,
            network_mode=network_mode,
            command=command,
            auto_remove=auto_remove,
            mounts=mounts,
            detach=detach,
            init=init,
            environment=env,
            hostname=hostname,
            volumes=volumes,
            devices=devices,
            privileged=privileged,
            cap_add=capabilities,
            extra_hosts=extra_hosts,
            **kwargs,
        )

    @classmethod
    def get_bindings(cls, container, new_bindings, conflicted=False, same=False):
        """
        check if received docker container obj has bindings that conflict/same with a given bindings
        according to the flags

        Args:
            container: docker container obj
            new_bindings: list of (port: [ip, port])
            conflicted: should check for conflicted bindings
            same: should check if has the same bindings

        Returns:
            list with conflicted/same bindings according to the flags
        """
        log.debug(f"Getting bindings for container {container}")
        bindings = []
        current_bindings = cls.get_container_port_bindings(container)
        for binding in current_bindings:
            existing_ip, existing_port = binding["ip"], binding["port"]
            if existing_port in new_bindings:
                new_ip = new_bindings[existing_port][0]
                if conflicted:
                    if (
                        (new_ip == "localhost" or new_ip == cls.LOOPBACK_IP)
                        and existing_ip != "localhost"
                        and existing_ip != cls.LOOPBACK_IP
                    ) or new_ip != existing_ip:
                        bindings.append((existing_ip, existing_port))
                elif same:
                    if (
                        (new_ip == "localhost" or new_ip == cls.LOOPBACK_IP)
                        and (
                            existing_ip == "localhost" or existing_ip == cls.LOOPBACK_IP
                        )
                    ) or new_ip == existing_ip:
                        bindings.append((existing_ip, existing_port))
        return bindings

    @staticmethod
    def get_container_port_bindings(container: Container):
        """
        examine the container HostConfig attribute and returns the port bindings if exist

        Args:
            container: docker object container

        Returns:
            list: list of bindings where every element is dictionary of {"ip": "x.x.x.x", "port": y (int)}
        """
        bindings = []
        host_config = container.attrs.get("HostConfig", {})
        port_bindings = host_config.get("PortBindings", {})
        if isinstance(port_bindings, dict):
            for port in port_bindings.keys():
                existing_ip, existing_port = port_bindings[port][0]["HostIp"], int(
                    port_bindings[port][0]["HostPort"]
                )
                bindings.append({"ip": existing_ip, "port": existing_port})
        return bindings

    def check_for_conflict_bindings(
        self,
        container_name: str,
        ports: list,
        image: str,
        delete_if_wrong_config: bool = False,
    ):
        """
        Check if there is already existing container with the same name, image and ports
        Args:
            delete_if_wrong_config: delete container if there is conflict
            container_name: name of the wanted container
            ports: open ports configuration of the container
            image: image repo and tag of the running container

        Returns:

        """
        log.debug(f"Checking for existing container {container_name}")
        container = self.get_container(container_name)
        # Todo: check that image name is corresponding to container.image with version and tag
        if container is None:
            return False
        conflicted_bindings = self.get_bindings(container, ports, conflicted=True)
        if conflicted_bindings or (
            len(container.image.tags) > 0 and image != container.image.tags[0]
        ):
            log.warning(
                f"container {container_name} has different configuration, creating new one"
            )
            self.stop_container(container_name, remove=delete_if_wrong_config)
            return False
        return True

    def start_container(self, container_name: str):
        """
        Start a stopped container
        Args:
            container_name: the name of the container

        """
        log.info(f"Stating container {container_name}")
        container = self.get_container(container_name)
        if container is None:
            log.warning(
                f"Can't start container {container_name}, can't find container "
            )
            return
        container.start()

    def restart_container(self, container_name: str):
        """
        Restarting container
        Args:
            container_name: name of the container

        """
        log.debug(f"Restarting container {container_name}")
        self.stop_container(container_name)
        self.start_container(container_name)

    @check_dockerd
    def create_host_config(self, **kwargs):
        """
        A wrapper function for the container tool
        """
        log.debug("Creating host configuration")
        port_bindings = kwargs.get("port_bindings", None)
        auto_remove = kwargs.get("auto_remove", False)
        docker_mounts = kwargs.get("mounts", {})
        binds = kwargs.get("binds", {})
        privileged = kwargs.get("privileged", False)
        devices = kwargs.get("devices", [])
        extra_hosts = kwargs.get("extra_hosts", {})
        capabilities = kwargs.get("capabilities", [])
        network_mode = kwargs.get("network_mode", None)
        init = kwargs.get("init", False)
        h_config = self._docker_APIClient.create_host_config(
            binds=binds,
            mounts=docker_mounts,
            port_bindings=port_bindings,
            auto_remove=auto_remove,
            init=init,
            devices=devices,
            privileged=privileged,
            cap_add=capabilities,
            extra_hosts=extra_hosts,
            network_mode=network_mode,
        )
        return h_config

    @check_dockerd
    def create_container(self, name: str, image: str, **kwargs) -> dict:
        """
        A wrapper function for the container tool
        """
        log.debug(f"Creating container {name} from image {image}")
        hostname = kwargs.pop("hostname", None)
        h_config = kwargs.pop("host_config", {})
        command = kwargs.pop("command", None)
        ports = kwargs.pop("ports", {})
        labels = kwargs.pop("labels", {})
        n_config = kwargs.pop("networking_config", {})
        b_volumes = kwargs.pop("volumes", [])
        env = kwargs.pop("environment", [])
        detach = kwargs.pop("detach", None)
        container_labels = {}
        container_labels.update(self._default_labels)
        container_labels.update(labels)
        container_id = self._docker_APIClient.create_container(
            image=image,
            command=command,
            name=name,
            labels=container_labels,
            hostname=hostname,
            networking_config=n_config,
            host_config=h_config,
            volumes=b_volumes,
            ports=list(ports),
            detach=detach,
            environment=env,
            **kwargs,
        )
        return container_id

    create_container.__doc__ += ContainerApiMixin.create_container.__doc__

    def get_all_containers(self, *args, **kwargs) -> list:
        """A wrapper function to get all containers from the container tool"""
        labels = kwargs.pop("labels", {})
        containers_labels = {}
        containers_labels.update(self._default_labels)
        containers_labels.update(labels)
        log.debug("Getting all containers")
        search_filter_label = []
        for k in containers_labels:
            v = containers_labels[k]
            search_filter_label.append(f"{k}={v}")
        filters = kwargs.pop("filters", {})
        kwargs["filters"] = filters
        return self._docker_client.containers.list(*args, **kwargs)

    get_all_containers.__doc__ += ContainerCollection.list.__doc__

    def stop_all_containers(self, labels: dict = None):
        """
        Stop all of our containers, that contains our labels
        Args:
            labels: stop by specific tag

        """
        containers = self.get_all_containers(labels=labels)
        for container in containers:
            container.stop()

    def get_container_repo_and_image(
        self, container_name: str
    ) -> (Optional[str], Optional[str], Optional[str]):
        """

        Args:
            container_name: the name of the container or id

        Returns:
            image name, repository and tag, if can't find container None

        """
        container = self.get_container(container_name)
        if container is None:
            log.error("can't snapshot: {container_name}, can't find container")
            return None, None, None
        full_repo = container.image.tags[0]
        repo, tag = full_repo.rsplit(":", 1)
        return container.image, repo, tag

    def commit_container(
        self, container_name: str, tag: str, repository: Optional[str] = None
    ) -> bool:
        """
        Commits the container
        Args:
            container_name: the name of the container
            repository: which repository to commit to,
                        if none will commit to the same repository
            tag: What tag for the new commit

        Returns: True if successful, False otherwise False

        """
        container = self.get_container(container_name)
        if container is None:
            log.error("can't commit container")
            return False
        if repository is None:
            full_repo = container.image.tags[0]
            repository, _ = full_repo.rsplit(":", 1)

        container.commit(repository=repository, tag=tag)
        return True

    def put_archive(self, container_name: str, path: str, archive: str) -> bool:
        """
        Insert a file or folder in this container using a tar archive as
        source.

        Args:
            container_name: the name of the container or ID
            path (str): Path inside the container where the file(s) will be
                extracted. Must exist.
            archive: tar file data to be extracted and pass to the container

        Returns:
            (bool): True if the call succeeds.

        """
        if not os.path.exists(archive):
            log.error(f"Archive {archive} not found!")
            raise OrchestratorException(f"Archive {archive} not found!")
        container = self.get_container(container_name)
        if container is None:
            log.error("Can't put archive")
            return False
        with open(archive, "rb") as file:
            success = container.put_archive(path, file.read())
        return success

    def get_container_ip(self, container_name, network: Optional[int]) -> Optional[str]:
        """
        Get the container ip on specified network
        Args:
            container_name: name or id of the container
            network: Optional network number if connected to many

        Returns:
            Ip or None if can't find

        """
        log.debug("getting container ip")
        container = self.get_container(container_name)
        if container is None:
            log.error("Can't get container ip")
            return None
        attrs = container.attrs["NetworkSettings"]["Networks"]
        if isinstance(network, int):
            return attrs[list(attrs.keys())[network]]["IPAddress"]
        else:
            return container.attrs["NetworkSettings"]["IPAddress"]

    def container_wait(
        self,
        name: str,
        timeout: Optional[int] = None,
        condition: Optional[str] = "not-running",
    ) -> dict:
        """
          Block until the container stops, then return its exit code. Similar to
         the ``docker wait`` command.
        Args:
             name: name of the container to block
             timeout (int): Request timeout
             condition (str): Wait until a container state reaches the given
                 condition, either ``not-running`` (default), ``next-exit``,
                 or ``removed``

         Returns:
             (dict): The API's response as a Python dictionary, including
                 the container's exit code under the ``StatusCode`` attribute.
        """
        container = self.get_container(name)
        if container is None:
            log.error("can't make container wait, can't find it")
            return {}
        kws = {"condition": condition}
        if timeout:
            kws["timeout"] = timeout
        return container.wait(**kws)

    @staticmethod
    def parse_mounts(mounts: Optional[dict]) -> List[Mount]:
        """
        Helper function to parse mounts for the container
        Args:
            mounts:

        Returns:
            List of the mounts objects

        """
        if mounts is None:
            return list()
        docker_mounts = []
        for key, value in mounts.items():
            docker_mounts.append(Mount(key, value))
        return docker_mounts
