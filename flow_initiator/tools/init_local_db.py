"""
   Copyright (C) Mov.ai  - All Rights Reserved
   Unauthorized copying of this file, via any medium is strictly prohibited
   Proprietary and confidential

   Developers:
   - Tiago Paulino (tiago@mov.ai) - 2020

    Initialize redis local storage with:
        System:PortsData
        System:PyModules

"""

from dal.models.message import Message
from dal.models.callback import Callback
import os, signal

def main():
    """initialize redis local db"""
    Message.export_portdata(db="local")
    Callback.export_modules()
    # TODO: this is a bit overkill, we should change how we are getting all the python packages/modules (without actually executing)
    # export module is launching a set of processes that might run unwanted code => Security risk
    os.kill(os.getpid(), signal.SIGKILL)


if __name__ == "__main__":
    main()
