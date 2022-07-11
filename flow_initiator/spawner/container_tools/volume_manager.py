"""
A file to manage virtual volumes
"""
from typing import Optional
from docker.errors import NotFound
from docker.models.volumes import Volume

from flow_initiator.spawner.container_tools import DockerBaseManager, check_dockerd
from movai_core_shared.logger import Log

log = Log.get_logger("VolumeManager")


class VolumeManager(DockerBaseManager):
    """
    A class to manager virtual volumes
    """

    def __init__(self, default_labels=None):
        super().__init__(default_labels)

    @check_dockerd
    def create_volume(self, name: str, labels: Optional[dict] = None) -> Volume:
        """
        Create new docker volume
        Args:
            name: The volume container_name
            labels: labels for the volume
        Returns:
            The volume created object.
        """
        log.info(f"Creating new volume: {name}")
        volume_labels = {}
        volume_labels.update(self._default_labels)
        if labels is not None:
            volume_labels.update(labels)

        return self._docker_client.volumes.create(name=name, labels=volume_labels)

    def get_or_create_volume(self, name: str, labels: Optional[dict] = None) -> Volume:
        """
        Get existing volume otherwise create new one
           Args:
               name: the volume container_name
               labels: labels for the volume
           Returns:
               The new/existing volume
        """
        log.debug(f"Requesting volume: {name}")
        volume = self.get_volume(name)
        if volume is None:
            volume = self.create_volume(name, labels)
        return volume

    @check_dockerd
    def get_volume(self, name: str) -> Optional[Volume]:
        """
        Get a volume by container_name
        Args:
            name: container_name of the volume
        Returns: volume or None if not found
        """
        log.debug(f"Getting volume: {name}")
        try:
            return self._docker_client.volumes.get(name)
        except NotFound:
            return None

    @check_dockerd
    def remove_volume(self, name: str, force: bool = False):
        """
        Delete volume by name
        Args:
            name: volume id
            force (bool): Force removal of volumes that were already removed
                out of band by the volume driver plugin.

        """
        log.info(f"Removing volume: {name}")
        volume = self.get_volume(name)
        if volume is None:
            log.warning(f"didn't found volume: {name}, can't remove it")
        volume.remove(force)
