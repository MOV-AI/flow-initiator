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
import os
import signal

from dal.models.callback import Callback
from dal.models.message import Message

###### Temp fix for: https://movai.atlassian.net/browse/BP-1216
import json
from dal.scopes.system import System
PYTHON_IMPORTS_FILE="python_imports.json"
######

def main():
    """initialize redis local db"""
    Message.export_portdata(db="local")

    ###### Temp fix for: https://movai.atlassian.net/browse/BP-1216
    # Comment out the full search and import of python modules
    # Callback.export_modules()

    # Here we upload the python modules that are already saved in the file
    # This is copy pasted from the Callback.export_modules() function
    try:
        # currently using the old api
        mods = System("PyModules", db="local")  # scopes('local').System['PyModules', 'cache']
    except Exception:  # pylint: disable=broad-except
        mods = System(
            "PyModules", new=True, db="local"
        )  # scopes('local').create('System', 'PyModules')

    with open(PYTHON_IMPORTS_FILE, "r") as f:
        mods.Value = json.load(f)
    ######

    # TODO: this is a bit overkill, we should change how we are getting all the python packages/modules (without actually executing)
    # export module is launching a set of processes that might run unwanted code => Security risk
    os.kill(os.getpid(), signal.SIGKILL)


if __name__ == "__main__":
    main()
