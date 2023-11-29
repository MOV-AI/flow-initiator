"""
   Copyright (C) Mov.ai  - All Rights Reserved
   Unauthorized copying of this file, via any medium is strictly prohibited
   Proprietary and confidential

   Developers:
   - Manuel Silva (manuel.silva@mov.ai) - 2020
   - Tiago Paulino (tiago@mov.ai) - 2020
   - Dor Marcous (Dor@mov.ai) - 2022
"""
import asyncio
from beartype import beartype
import os
import pickle

import aioredis
import rospy

from movai_core_shared.logger import Log

from dal.scopes.robot import Robot
from dal.models.lock import Lock
from dal.movaidb import RedisClient

from .spawner import Spawner

# importing database profile automatically registers the database connections
from rosgraph_msgs.msg import Log as RosOutMsg

USER_LOGGER = Log.get_user_logger("Core")


class SpawnerCore:
    """Core class to run movai"""

    RUNNING = False

    @beartype
    def __init__(self, spawner: Spawner):
        """
        Core constructor
        Args:
            fargs:  arguments for initialization
        """
        type(self).RUNNING = True
        self.spawner = spawner
        self._logger = Log.get_user_logger("movaicore")
        self.robot = Robot()
        del self.robot.Actions  # local  set
        del self.robot.fleet.Actions  # global set
        # Should we add FLEET_NAME? Where?
        self.robot.set_ip(os.getenv("PUBLIC_IP", self.robot.IP))  # local set
        self.robot.set_name(os.getenv("DEVICE_NAME", self.robot.RobotName))  # local set
        self._logger.info(f"Robot {self.robot.RobotName} started.")
        self.databases = None
        self.conn = None
        self.conn_sub = None
        self.conn_local = None
        self.conn_local_sub = None
        self.subscribers = [
            {
                "key": f"Robot:{self.robot.name},Actions:",
                "callback": self.callback,
                "channel": None,
                "db_pop": "conn",
                "db_sub": "conn_sub",
            },
            {
                "key": f"Robot:{self.robot.name},Actions:",
                "callback": self.callback,
                "channel": None,
                "db_pop": "conn_local",
                "db_sub": "conn_local_sub",
            },
        ]
        # [{"key": "key_pattern", "callback": callback, "channel": None, "db_pop": "db_pop", "db_sub": "db_sub"}, ]
        # db_pop: connection to pop the key
        # db_sub: connection to subscribe to key

        # subscribe to /rosout_agg
        rospy.init_node("movai_logger", anonymous=True)
        rospy.Subscriber("rosout_agg", RosOutMsg, self._rosout_callback)

        self.tasks = []

    def _rosout_callback(self, msg):
        """
        Catch ROS log output and log to system logger
        Args:
            msg: the ros message

        Returns: None

        """
        level = msg.level
        if level == 2:  # info
            USER_LOGGER.info(msg.msg, name=msg.name, function=msg.function)
        elif level == 4:  # warning
            USER_LOGGER.warning(msg.msg, name=msg.name, function=msg.function)
        elif level == 8:  # error
            USER_LOGGER.error(msg.msg, name=msg.name, function=msg.function)
        elif level == 16:  # fatal/critical
            USER_LOGGER.critical(msg.msg, name=msg.name, function=msg.function)
        else:  # default debug
            USER_LOGGER.debug(msg.msg, name=msg.name, function=msg.function)

    async def connect(self) -> None:
        """
        Create database connections
        Returns: None

        """

        self.databases = await RedisClient.get_client()

        self.conn = self.databases.db_global  # connection to global database
        # await self.conn.client_setname(self.robot.RobotName + '_movai_core')

        # subscribe to slave db notifications
        _conn_sub = await self.databases.slave_pubsub.acquire()
        self.conn_sub = aioredis.Redis(_conn_sub)

        # connection to local db
        self.conn_local = self.databases.db_local
        await self.conn_local.client_setname("movai_core")

        # subscribe to local db notifications
        _conn_local_sub = await self.databases.local_pubsub.acquire()
        self.conn_local_sub = aioredis.Redis(_conn_local_sub)

    async def task_subscriber(
        self, subscriber: dict, connection: aioredis.Redis
    ) -> None:
        """
        Calls a callback every time it gets a message
        Args:
            subscriber (dict): the subscriber dict with the configuration.
            connection (aioredis.Redis): the connection

        Returns: None

        """
        channel = subscriber["channel"][0]
        callback = subscriber["callback"]

        while self.RUNNING:
            try:
                await asyncio.wait_for(channel.wait_message(), timeout=1.0)
                msg = await channel.get()
                if callback:
                    await callback(msg, connection)
            except asyncio.TimeoutError:
                pass

    async def register_sub(self) -> None:
        """
        Subscribe to key.
        Returns: None

        """
        for subscriber in self.subscribers:
            self._logger.info(
                f"Subscribing to key: {subscriber['key']} - {subscriber['db_pop']} - {subscriber['db_sub']}"
            )
            key = subscriber["key"]
            conn = getattr(self, subscriber["db_pop"])
            conn_sub = getattr(self, subscriber["db_sub"])
            res = await conn_sub.psubscribe("__keyspace@*__:*%s*" % key)
            subscriber["channel"] = res
            asyncio.create_task(self.task_subscriber(subscriber, conn))

    async def unregister_sub(self) -> None:
        """
        Unsubscribe key
        Returns: None

        """
        self._logger.info("Unregistering subscribers.")
        for subscriber in self.subscribers:
            conn_sub = getattr(self, subscriber["db_sub"])
            await conn_sub.punsubscribe("__keyspace@*__:*%s*" % subscriber["key"])

    async def callback(self, msg: tuple, connection: aioredis.Redis) -> None:
        """
        Callback that processes commands coming from redis
        Args:
            msg (tuple): the  redis message
            connection (aioredis.Redis): the connection

        Returns: None

        """
        _, key = msg[0].decode("utf-8").split(":", 1)
        if msg[1].decode("utf-8") == "rpush":
            if connection:
                _result = await connection.lpop(key)
                try:
                    result = _result.decode("utf-8")
                except UnicodeDecodeError:
                    result = pickle.loads(_result)
                await self.spawner.process_command(result)

    async def stop(self) -> None:
        """
        Calls all methods necessary to stop movai core.
        Returns: None

        """
        self._logger.info("STOP Called.")
        await self.unregister_sub()
        self.conn.close()
        # terminate processes launched by the spawner
        await self.spawner.stop()
        tasks = [
            task for task in asyncio.all_tasks() if task is not asyncio.current_task()
        ]
        list(map(lambda task: task.cancel(), tasks))
        await asyncio.gather(*tasks, return_exceptions=True)

        # clean enabled locks pool to finish any hanging threads
        Lock.enabled_locks = []

    def shutdown(self):
        """
        Shutdown function, closing everything.
        Returns: None

        """
        self.RUNNING = False

    async def spin(self) -> None:
        """
        Runs the main loop. Exiting spin stops movai core.
        Returns: None

        """
        await self.connect()
        await self.register_sub()
        while self.RUNNING:
            # robot keep alive
            await self.spawner.fn_update_robot()
            await asyncio.sleep(3)  # Give time to other tasks to run.
        self._logger.info("STOPPING MOVAICORE AND ALL ASSOCIATED PROCESSES")
        await self.stop()

    def run(self):
        """Starts running the object."""
        asyncio.create_task(self.spin())
