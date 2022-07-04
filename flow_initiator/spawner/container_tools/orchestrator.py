"""
Mov.Ai orchestrator
"""
import io
import tarfile
from socket import gethostname
from time import localtime
from typing import Optional
from flow_initiator.spawner.container_tools import (
    ContainerManager,
    NetworkManager,
    VolumeManager,
    ImageManager,
)
from flow_initiator.spawner.exceptions import (
    OrchestratorException,
    FailedUpgradeCertificate,
)
from movai_core_shared.logger import Log

log = Log.get_logger("orchestrator")


class Orchestrator:
    """
    An Orchestrator that manage all the container operation
    """

    docker_registry = property(lambda self: self._containers.docker_registry)

    def __init__(self, labels=None):
        self._images = ImageManager(labels)
        self._networks = NetworkManager(labels)
        self._volumes = VolumeManager(labels)
        self._containers = ContainerManager(labels)
        net_name = f"shared-{gethostname()}"
        try:
            self._shared_network = self._networks.get_or_create_network(net_name)
        except OrchestratorException:
            log.critical("Can't create new network")

    def run_container(
        self,
        name: str,
        hostname: str,
        image: str,
        network: str = None,
        network_id: str = None,
        command: str = None,
        ports: list = None,
        auto_remove: bool = False,
        mounts: Optional[dict] = None,
        privileged: bool = False,
        network_mode: str = "bridge",
        **kwargs,
    ):
        """
        Start a new container.
        Args:
            name: the name of the container
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
        log.info(f"Running container: {name}")
        volumes = kwargs.pop("volumes", dict())
        extra_hosts = kwargs.pop("extra_hosts", dict())
        env = kwargs.pop("env", list())
        devices = kwargs.pop("devices", list())
        capabilities = kwargs.pop("capabilities", list())
        labels = kwargs.pop("labels", dict())

        try:
            existing_container = self._containers.get_container(name)
            if existing_container is not None:
                self._networks.attach_container_to_network(
                    container=existing_container,
                    network_name=network or network_id,
                    aliases=[hostname],
                )
                if self._containers.check_for_conflict_bindings(
                    name, ports, image, delete_if_wrong_config=True
                ):
                    log.info(f"Restarting exising container: {name}")
                    return self._containers.restart_container(name)

            image_file = self._images.get_image(image)
            if image_file is None:
                log.error(f"Can't get image {image}")
                return
            log.info(f"Creating new container: {name}")

            docker_mounts = self._containers.parse_mounts(mounts)

            log.debug(f"Running container with network mode {network_mode}")
            if network_mode == "bridge":
                containers_dict = self.create_container_with_bridge(
                    auto_remove,
                    capabilities,
                    command,
                    devices,
                    docker_mounts,
                    env,
                    extra_hosts,
                    hostname,
                    image,
                    labels,
                    name,
                    network,
                    network_id,
                    network_mode,
                    ports,
                    privileged,
                    volumes,
                    **kwargs,
                )
                if containers_dict is None or "Id" not in containers_dict:
                    log.error(f"can't start container {name}")
                    return

                self._containers.start_container(containers_dict["Id"])

            else:
                self._containers.run_container(
                    image=image,
                    container_name=name,
                    labels=labels,
                    network_mode=network_mode,
                    command=command,
                    auto_remove=auto_remove,
                    mounts=docker_mounts,
                    detach=True,
                    init=True,
                    env=env,
                    hostname=hostname,
                    volumes=volumes,
                    devices=devices,
                    privileged=privileged,
                    capabilities=capabilities,
                    extra_hosts=extra_hosts,
                    **kwargs,
                )
        except OrchestratorException as e:
            for container in self._containers.get_all_containers():
                if "haproxy" in container.name and container.status == "running":
                    same_bindings = self._containers.get_bindings(
                        container, ports, same=True
                    )
                    for binding in same_bindings:
                        log.error(
                            f"Container {container.name} is currently running and occupying {binding[0]}:{binding[1]}"
                        )

            log.error(f"{e.__class__.__qualname__} {e}")

    def create_container_with_bridge(
        self,
        auto_remove: bool,
        capabilities: list,
        command: str,
        devices: list,
        docker_mounts: list,
        env: list,
        extra_hosts: dict,
        hostname: str,
        image: str,
        labels: dict,
        name: str,
        network: str,
        network_id: str,
        network_mode: str,
        ports: list,
        privileged: bool,
        volumes: dict,
        **kwargs,
    ) -> dict:
        """
        Help function for creating with virtual network bridge configuration
        Args:
            name: the name of the container
            hostname: alias configuration for the container network
            image: image name for the container
            network: network name for the container
            network_id: network id for the container, instead of network id
            command: optional command to run the container
            ports: open network ports for this container, list of (port: [ip, port])
            auto_remove (bool): if to remove the container, when it's stopped.
            labels (dict): label for the container
            env (list): environment variables for the container
            volumes (dict): volumes to load
            privileged (bool): if to run container in privileged mode
            devices (list): devices to give permission
            network_mode: type of network mode, default "bridge"
            extra_hosts (dict): extra hosts ips to connect the container
            capabilities (list): grant capabilities for the container
            docker_mounts: mounts drive option

        Returns:
            A dict with the new container id

        """
        if network is None and network_id is not None:
            # if no network name, fine network name by id
            network = self._networks.get_network(network_id).name
        if network is None:
            # if no network name and no network id, or it can't find network by id
            network = self._shared_network.name
        endpoint_config = self._networks.create_endpoint_config(aliases=[hostname])
        n_config = self._networks.create_network_config({network: endpoint_config})
        h_config = self._containers.create_host_config(
            binds=volumes,
            mounts=docker_mounts,
            port_bindings=ports,
            auto_remove=auto_remove,
            init=True,
            devices=devices,
            privileged=privileged,
            cap_add=capabilities,
            extra_hosts=extra_hosts,
            network_mode=network_mode,
        )
        b_volumes = [i["bind"] for i in volumes.values()]
        containers_dict = self._containers.create_container(
            image=image,
            command=command,
            name=name,
            labels=labels,
            hostname=hostname,
            networking_config=n_config,
            host_config=h_config,
            volumes=b_volumes,
            ports=list(ports or {}),
            detach=True,
            environment=env,
            **kwargs,
        )
        return containers_dict

    def remove_volume(self, volume: str, force: bool = False):
        """
        Delete volume by name
        Args:
            volume: volume id or name
            force (bool): Force removal of volumes that were already removed
                out of band by the volume driver plugin.

        """

        return self._volumes.remove_volume(volume, force)

    def pull_image(self, image: str):
        """
        Pull container image wrapper
        Args:
            image: name of the image, can add specific tag

        Returns:
            The image file

        """
        repo, tag = self._images.extract_image_name(image)
        return self._images.pull_image(repo, tag)

    def container_create_volume(self, volume: str, labels: Optional[dict] = None):
        """
        Create virtual volumes wrapper
        Args:
            labels: labels for the new volume
            volume: volume name

        Returns:
            The new volume object.
        """
        return self._volumes.create_volume(volume, labels)

    def container_create_network(self, network: str, labels: Optional[dict] = None):
        """
        Create virtual network wrapper
        if a network already exists, will return the the existing network
        Args:
            labels: labels for the new network
            network: network name

        Returns:
            str: short_id of the new network
        """
        return self._networks.get_or_create_network(network, labels).short_id

    def container_stop(self, name: str, remove: bool = False):
        """
        Stop Container wrapper
        Args:
            name: name of the container
            remove (bool): if to delete the container after stop

        """
        self._containers.stop_container(name, remove)

    def image_prune(self) -> None:
        """
        Remove dangling images
        """
        log.info("Removing dangling images")
        self._images.prune_images({"dangling": True})

    def image_remove(self, repo: str, tag: str, **kwargs):
        self._images.remove_image(repo, tag, **kwargs)

    image_remove.__doc__ = ImageManager.remove_image.__doc__

    def image_tag(self, image_name: str, new_repo: str, new_tag: str) -> None:
        """
        wrapper to tag image
        Args:
            image_name: the current repo name and tag
            new_repo: the new repo
            new_tag: the new tag

        """
        image = self._images.get_image(image_name)
        if image is None:
            log.error(f"Image: {image_name} not found, can't tag")
            raise OrchestratorException("Image not found")
        elif new_tag in image.tags:
            log.error(f"tag: {new_tag} already exist can't tag")
            raise OrchestratorException("tag already exist")
        self._images.tag_image(image, new_tag, new_tag)

    def container_snapshot(
        self, container_name: str, latest_tag: str = "latest", snapshot_tag: str = None
    ) -> Optional[str]:
        """
        Save a snapshot of a container
        Args:
            container_name: the name of the container
            latest_tag:
            snapshot_tag:

        Returns:
            The snapshot tag

        """
        image_name, repo, _ = self._containers.get_container_repo_and_image(
            container_name
        )
        if image_name is None or repo is None:
            log.error("can't snapshot: {container_name}, can't find get information")
            return None
        if snapshot_tag is None:
            _lt = localtime()
            snapshot_tag = f"{_lt.tm_year}{_lt.tm_mon}{_lt.tm_mday}{_lt.tm_hour}{_lt.tm_min}{_lt.tm_sec}"
        commit_image = self._images.get_image(image_name)
        self._containers.commit_container(container_name, repo, snapshot_tag)
        self._images.tag_image(commit_image, new_repo=repo, new_tag=snapshot_tag)
        return snapshot_tag

    def container_execute_command(self, name: str, cmd: str):
        """
        Run a command on a running container
        Args:
            name: name of the container
            cmd: command to run

         Returns:
        (ExecResult): A tuple of (exit_code, output)

        """
        return self._containers.container_execute_command(name, cmd)

    container_execute_command.__doc__ = (
        ContainerManager.container_execute_command.__doc__
    )

    def container_attach_network(
        self, container_name: str, hostname: str, network: str
    ):
        return self._networks.attach_container_to_network(
            container_name, network, aliases=[hostname]
        )

    container_attach_network.__doc__ = (
        NetworkManager.attach_container_to_network.__doc__
    )

    def container_get(self, container_name: str):
        """
        Get container by name
        Args:
            container_name: Container name or ID.

        Returns:
            Container object if found, otherwise None

        """
        return self._containers.get_container(container_name)

    def container_apt_update(self, container_name: str, run_as_sudo: bool):
        """will run apt update inside the container.

        Args:
            container_name (str): the name of the container to be updated.
            run_as_sudo (bool): run update as sudo or not. Defaults to True.

        Returns:
            Tuple[bool, str]: bool indicates if it's whether succeeded or not.
                            str will indicate the fail message in case failed.
        """
        cmd_prefix = ""
        if run_as_sudo:
            cmd_prefix = "sudo -E"
        status, output = self.container_execute_command(
            container_name, f"{cmd_prefix} apt update"
        )

        return status == 0, output.decode().strip()

    def container_upgrade_certificate(self, container_name: str, run_as_sudo: bool):
        """will upgrade certificate inside the container and log

        Args:
            container_name (str): the name of the container to be updated.
            run_as_sudo (bool): run update as sudo or not. Defaults to True.

        Returns:
            Tuple[bool, str]: bool indicates if it's whether succeeded or not.
                            str will indicate the fail message in case failed.
        """
        cmd_prefix = ""
        if run_as_sudo:
            cmd_prefix = "sudo -E"
        status, output = self.container_execute_command(
            container_name, f"{cmd_prefix} apt upgrade ca-certificates -y"
        )

        return status == 0, output.decode().strip()

    def container_update_and_check_certificate(
        self, container_name: str, run_as_sudo: bool = True
    ) -> bool:
        """will run apt update in container and check for failures.
        in case there was a certificate issue it will upgrade it and retry update.

        Args:
            container_name (str): the name of the container to be updated.
            run_as_sudo (bool, optional): run update as sudo or not. Defaults to True.

        Raises:
            FailedUpgradeCertificate: in case there is failed certificate upgrade.

        Returns:
            bool: whether the update succeed or not.
        """
        apt_succeeded, output = self.container_apt_update(container_name, run_as_sudo)
        if not apt_succeeded:
            log.info("failed first attempt to update package index")
            log.debug(f"Output: {output}")
            if output.find("Certificate verification failed") != -1:
                certificate_upgraded, output = self.container_upgrade_certificate(
                    container_name, run_as_sudo
                )
                if not certificate_upgraded:
                    log.warning("failed upgrading certificates")
                    log.debug(f"Output: {output}")
                    raise FailedUpgradeCertificate()
                else:
                    log.info(f"Successfully upgraded certificates")
                    apt_succeeded, output = self.container_apt_update(
                        container_name, run_as_sudo
                    )
                    if not apt_succeeded:
                        log.warning("failed to update package index")
                        log.debug(f"Output: {output}")
                    else:
                        log.info(f"Successfully updated package index")

        return apt_succeeded

    def remove_network(self, network_id: str):
        """removes network from docker networks.

        Args:
            network_id (str): network id that need to be removed.
        """
        return self._networks.remove_network(network_id)

    def container_put_directory(self, name: str, path: str, directory: str):
        """
         Upload a directory to a container
        same as put_file, since directories go recursively
        just easier to read code with this name
        Args:
            name:
            path:
            directory:

        Returns:

        """

        self.container_put_file(name, path, directory)

    def container_put_file(self, name: str, path: str, file: str) -> False:
        """
        Upload a single file to a container
        Args:
            name: of the container
            path: file location
            file: name of the file

        Returns:
            True if successful, otherwise false

        """
        bytes_stream = io.BytesIO()
        tar_file = tarfile.open(fileobj=bytes_stream, mode="w", bufsize=512)
        # recursive by default, that's why directory is the same as file
        tar_file.add(file)

        container = self.container_get(name)
        if container is None:
            log.error(f"Can't copy file to container :{name}, can't find container")
            return False

        container.exec_run(f"mkdir -p {path}", stdout=False, stderr=False)
        success = container.put_archive(path, bytes_stream.getvalue())

        return success

    def container_put_archive(self, name: str, path: str, archive: str):
        self.container_execute_command(name, f"mkdir -p {path}")
        return self._containers.put_archive(name, path, archive)

    container_put_archive.__doc__ = ContainerManager.put_archive.__doc__

    def container_ip(self, container_name: str, network):
        return self._containers.get_container_ip(container_name, network)

    container_ip.__doc__ = ContainerManager.get_container_ip.__doc__

    def container_remove(self, container_name):
        self._containers.remove_container(container_name)

    container_remove.__doc__ = ContainerManager.remove_container.__doc__

    def container_rollback(
        self, container_name: str, tag: str, restart=False, rollback_tag: str = "latest"
    ):
        """
        Create a image tag to use as a rollback image, from a container
        Args:
            container_name: the container name that will be taken the image from
            tag: the specific tag,
            -- restart: deprecated --
            rollback_tag: the new tag

        Returns:

        """
        image_name, repo, _ = self._containers.get_container_repo_and_image(
            container_name
        )

        if image_name is None or repo is None:
            log.error("Container not found")
            raise OrchestratorException("Container not found")
        rollback_image = f"{repo}:{tag}"
        image = self._images.get_image(rollback_image)
        if image is None:
            log.error("Tag not found on requested image")
            raise OrchestratorException("Tag not found on requested image")
        self._images.tag_image(image, repo, rollback_tag)

    def containers_stop(self, labels: dict = None):
        self._containers.stop_all_containers(labels)

    containers_stop.__doc__ = ContainerManager.stop_all_containers.__doc__

    def image_commit(self, container_name: str, tag: str):
        """
        Commits the image from a running container.
        Args:
            container_name: the name of the container  or ID
            tag: the new tag of the commit

        Returns:
            True if successful

        """
        return self._containers.commit_container(container_name=container_name, tag=tag)

    def container_wait(self, name: str, timeout: int, condition: str = "not-running"):
        return self._containers.container_wait(name, timeout, condition)

    container_wait.__doc__ = ContainerManager.container_wait.__doc__

    container_launch = run_container

    def volume_remove(self, param, force):
        """
        remove volume
        Args:
            param: what volume to remove
            force: if to remove forcefully

        """
        self._volumes.remove_volume(param, force)

    def get_container_state(self, container: str):
        return self._containers.get_container_state(container)

    get_container_state.__doc__ = ContainerManager.get_container_state.__doc__
