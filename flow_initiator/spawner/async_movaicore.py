"""
   Copyright (C) Mov.ai  - All Rights Reserved
   Unauthorized copying of this file, via any medium is strictly prohibited
   Proprietary and confidential

   Developers:
   - Manuel Silva (manuel.silva@mov.ai) - 2020
   - Tiago Paulino (tiago@mov.ai) - 2020
   - Dor Marcous (Dor@mov.ai) - 2022
"""
import argparse
import asyncio
import os
import pickle
import traceback

import aioredis

import rospy
from dal.movaidb import Lock
from dal.movaidb import RedisClient
from dal.scopes import Robot
from .async_spawner import Spawner

# importing database profile automatically registers the database connections
from rosgraph_msgs.msg import Log as RosOutMsg
from movai_core_shared.logger import Log

LOGGER = Log.get_logger("spawner.mov.ai")


class Core:
    """Core class to run movai"""

    RUNNING = False

    def __init__(self, fargs: argparse.Namespace):
        type(self).RUNNING = True

        # self.loop = uvloop.new_event_loop()
        # asyncio.set_event_loop(self.loop)
        self.loop = asyncio.get_event_loop()
        self.loop.set_exception_handler(self.handle_exception)

        self.robot = Robot()
        del self.robot.Actions  # local  set
        del self.robot.fleet.Actions  # global set
        # Should we add FLEET_NAME? Where?
        self.robot.set_ip(os.getenv("PUBLIC_IP", self.robot.IP))  # local set
        self.robot.set_name(os.getenv("DEVICE_NAME", self.robot.RobotName))  # local set
        LOGGER.info(f"Robot {self.robot.RobotName} started.")
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
        self.spawner = Spawner(self.loop, self.robot, fargs.verbose)

        # subscribe to /rosout_agg
        rospy.init_node("movai_logger", anonymous=True)
        rospy.Subscriber("rosout_agg", RosOutMsg, self._rosout_callback)

        self.tasks = []

    def handle_exception(self, loop, context):
        """Handle Exceptions"""
        msg = context.get("exception", context["message"])
        tb_str = traceback.format_exception(
            etype=type(msg), value=msg, tb=msg.__traceback__
        )
        LOGGER.error("\n" + "".join(tb_str))

    def _rosout_callback(self, msg):
        """Catch ROS log output and log to system logger"""
        level = msg.level
        if level == 2:  # info
            LOGGER.info(msg.msg, name=msg.name, function=msg.function)
        elif level == 4:  # warning
            LOGGER.warning(msg.msg, name=msg.name, function=msg.function)
        elif level == 8:  # error
            LOGGER.error(msg.msg, name=msg.name, function=msg.function)
        elif level == 16:  # fatal/critical
            LOGGER.critical(msg.msg, name=msg.name, function=msg.function)
        else:  # default debug
            LOGGER.debug(msg.msg, name=msg.name, function=msg.function)

    async def connect(self) -> None:
        """Create database connections"""

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
        self, subscriber: str, connection: aioredis.Redis
    ) -> None:
        """Calls a callback every time it gets a message."""
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
        """Subscribe to key."""
        for subscriber in self.subscribers:
            LOGGER.info(
                f"Subscribing to key: {subscriber['key']} - {subscriber['db_pop']} - {subscriber['db_sub']}"
            )
            key = subscriber["key"]
            conn = getattr(self, subscriber["db_pop"])
            conn_sub = getattr(self, subscriber["db_sub"])
            res = await conn_sub.psubscribe("__keyspace@*__:*%s*" % key)
            subscriber["channel"] = res
            self.loop.create_task(self.task_subscriber(subscriber, conn))

    async def unregister_sub(self) -> None:
        """Unsubscribe key"""
        LOGGER.info("Unregistering subscribers.")
        for subscriber in self.subscribers:
            conn_sub = getattr(self, subscriber["db_sub"])
            await conn_sub.punsubscribe("__keyspace@*__:*%s*" % subscriber["key"])

    async def callback(self, msg: tuple, connection: aioredis.Redis) -> None:
        """Callback that processes commands coming from redis"""
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
        """Calls all methods necessary to stop movai core."""
        LOGGER.info("STOP Called.")
        await self.unregister_sub()
        self.conn.close()
        # terminate processes launched by the spawner
        await self.spawner.stop()
        tasks = [
            task
            for task in asyncio.Task.all_tasks()
            if task is not asyncio.tasks.Task.current_task()
        ]
        list(map(lambda task: task.cancel(), tasks))
        await asyncio.gather(*tasks, return_exceptions=True)

        # clean enabled locks pool to finish any hanging threads
        Lock.enabled_locks = []

    def run(self):
        self.loop.run_until_complete(self.spin())
        # will exit later
        self.loop.stop()

    def shutdown(self):
        self.RUNNING = False

    async def spin(self) -> None:
        """Runs the main loop. Exiting spin stops movai core."""
        await self.connect()
        await self.register_sub()
        while self.RUNNING:
            # robot keep alive
            await self.spawner.fn_update_robot()
            await asyncio.sleep(3)  # Give time to other tasks to run.
        LOGGER.info("STOPPING MOVAICORE AND ALL ASSOCIATED PROCESSES")
        await self.stop()
