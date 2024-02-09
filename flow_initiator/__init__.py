"""
   Copyright (C) Mov.ai  - All Rights Reserved
   Unauthorized copying of this file, via any medium is strictly prohibited
   Proprietary and confidential

   Developers:
   - Dor Marcous  (dor@mov.ai) - 2021

    Spawner module initialization
"""
import signal
import argparse
from dal.movaidb import RedisClient
from .spawner import SpawnerManager


def main():
    """spawner entrypoint"""
    RedisClient.enable_db("db_global")

    sig_handler = lambda sig, *_: app.shutdown()
    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    parser = argparse.ArgumentParser(description="MOV.ai spawner")
    parser.add_argument(
        "-v",
        "--verbose",
        help="increase output verbosity",
        action="store_true",
        dest="verbose",
    )
    parser.add_argument(
        "--version",
        help="spawner version to use (1 or 2)",
        type=int,
        dest="version",
        default=1,
    )
    args = parser.parse_args()
    app = SpawnerManager(args)
    return app.run()
