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
from dal.om import Callback
from dal.om import Message


def main():
    """initialize redis local db"""
    Message.export_portdata(db="local")
    Callback.export_modules()


if __name__ == "__main__":
    main()
