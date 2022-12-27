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
import json

import aioredis
import zmq.asyncio
import rospy

from movai_core_shared.logger import Log, LogAdapter
from movai_core_shared.envvars import MOVAI_SPAWNER_FILE_SOCKET, MOVAI_ZMQ_SOCKET
from movai_core_shared.core.zmq_client import create_certificates
from dal.scopes.robot import Robot
from dal.models.lock import Lock
from dal.movaidb import RedisClient

from .async_spawner import Spawner

# importing database profile automatically registers the database connections
from rosgraph_msgs.msg import Log as RosOutMsg

LOGGER = Log.get_logger("spawner.mov.ai")
USER_LOGGER = LogAdapter(LOGGER)


class Core:
    """Core class to run movai"""

    RUNNING = False

    def __init__(self, fargs: argparse.Namespace):
        """
        Core constructor
        Args:
            fargs:  arguments for initialization
        """
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
        self.spawner = Spawner(self.loop, self.robot, fargs.verbose, "flow-private")

        # subscribe to /rosout_agg
        rospy.init_node("movai_logger", anonymous=True)
        rospy.Subscriber("rosout_agg", RosOutMsg, self._rosout_callback)

        self.tasks = []

    def handle_exception(self, loop, context):
        """
        Handle Exceptions for all the threads
        Args:
            loop: event loop
            context: the context of the exception

        Returns: None

        """
        msg = context.get("exception", context["message"])
        tb_str = traceback.format_exception(etype=type(msg), value=msg, tb=msg.__traceback__)
        USER_LOGGER.error("\n" + "".join(tb_str))

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
        """
        Unsubscribe key
        Returns: None

        """
        LOGGER.info("Unregistering subscribers.")
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

    @staticmethod
    def close_port(sockets: list, context: zmq.Context) -> None:
        """
        Close all the ports
        Args:
            sockets: list of ZMQ ports
            context: the context that been used to open them

        Returns: None

        """
        for socket in sockets:
            if isinstance(socket, zmq.Socket):
                socket.close()
        context.terminate(1)

    async def ports_loop(self):
        """
        Async method for the ports loop
        Getting request from ports, and respond to the sender

        """
        context = zmq.asyncio.Context()
        file_socket = None
        tcp_socket = None
        try:
            poller = zmq.asyncio.Poller()
            # encrypted tcp port config
            tcp_socket = context.socket(zmq.ROUTER)
            tcp_socket.bind(f"tcp://*:{MOVAI_ZMQ_SOCKET}")
            public_key, secret_key = create_certificates("/tmp/", "key")
            tcp_socket.curve_publickey = public_key
            tcp_socket.curve_secretkey = secret_key
            tcp_socket.setsockopt(zmq.CURVE_SERVER, True)
            poller.register(tcp_socket, zmq.POLLIN)
            self.robot.set_pub_key(public_key.decode("utf8"))  # local set
            # local file socket config
            file_socket = context.socket(zmq.ROUTER)
            file_socket.bind(MOVAI_SPAWNER_FILE_SOCKET)
            poller.register(file_socket, zmq.POLLIN)
        except OSError as e:
            LOGGER.error("failed to init to spawner file socket")
            LOGGER.error(e)
            self.close_port([file_socket, tcp_socket], context)
            return
        while self.RUNNING and file_socket:
            try:
                sock = dict(await poller.poll())
                if file_socket in sock:
                    self.loop.create_task(self._handle_socket(file_socket))
                if tcp_socket in sock:
                    self.loop.create_task(self._handle_socket(tcp_socket))
            except TypeError:
                continue
            except zmq.ZMQError:
                continue
        self.close_port([file_socket], context)

    async def _handle_socket(self, server: zmq.Socket):
        """
        Handler for the zmq socket
        Args:
            server (zmq.Socket): the socket that received the message

        Returns: None

        """
        # receive data
        req_msg = await server.recv_multipart()
        if len(req_msg) == 3:
            # in case sender just use send
            msg_index = 2
        else:
            # in case when sending json
            msg_index = 1
        buffer = req_msg[msg_index]
        if buffer is None:
            return
        LOGGER.info(f"<- {buffer}")
        try:
            request = json.loads(buffer)
            self.loop.create_task(self.spawner.process_command(request))
            req_msg[msg_index] = "Got request & successfully proccessed".encode("utf8")
        except json.JSONDecodeError as e:
            LOGGER.error(f"can't parse command: {buffer}")
            LOGGER.error(e)
            req_msg[msg_index] = "can't parse command: {buffer}".encode("utf8")
        finally:
            await server.send_multipart(req_msg)

    async def stop(self) -> None:
        """
        Calls all methods necessary to stop movai core.
        Returns: None

        """
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
        """
        Running function, start the loop
        Returns: None

        """
        self.loop.run_until_complete(self.spin())
        # will exit later
        self.loop.stop()

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

        self.loop.create_task(self.ports_loop())
        while self.RUNNING:
            # robot keep alive
            await self.spawner.fn_update_robot()
            await asyncio.sleep(3)  # Give time to other tasks to run.
        LOGGER.info("STOPPING MOVAICORE AND ALL ASSOCIATED PROCESSES")
        await self.stop()
