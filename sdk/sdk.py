"""
   Copyright (C) Mov.ai  - All Rights Reserved
   Unauthorized copying of this file, via any medium is strictly prohibited
   Proprietary and confidential

   Developers:
   - Dor Marcous (dor@mov.ai) - 2022
"""

import json
import os
import zmq

MOVAI_ZMQ_TIMEOUT_MS = os.getenv("MOVAI_ZMQ_TIMEOUT_MS", 10000)
MOVAI_SOCKET = os.getenv("MOVAI_INNER_SOCKET", "ipc:///run/movai/movai.sock")

"""
How to use:
sdk.module.function(params...)
sdk.__getattr__(module).__getattr__(function).__call__(params...)
"""

class _Cmd(object):

    def __init__(self, module, command, callback):
        self._mod = module
        self._cmd = command
        self._callback = callback

    def __call__(self, **params):
        return self._callback(self._mod, self._cmd, **params)


class _Mod(object):

    def __init__(self, module, callback):
        self._mod = module
        self._callback = callback

    def __getattr__(self, name):
        return _Cmd(self._mod, name, self._callback)


class Sdk(object):

    def __init__(self, socket_add: str = MOVAI_SOCKET):
        self._socket = None
        self.ctx = None
        self.socket_add = socket_add

    def init_port(self):
        self.ctx = zmq.Context()
        self._socket = self.ctx.socket(zmq.REQ)
        self._socket.setsockopt(zmq.IDENTITY, "sdk_req".encode('utf8'))
        self._socket.setsockopt(zmq.RCVTIMEO, int(MOVAI_ZMQ_TIMEOUT_MS))
        self._socket.connect(self.socket_add)

    def __getattr__(self, name):
        return _Mod(name, self._request)

    def _request(self, _mod: str, _cmd: str, timeout_ms: int = None, **params):
        self.init_port()
        if timeout_ms is not None:
            self._socket.setsockopt(zmq.RCVTIMEO, int(timeout_ms))
        req_data = {
            'request': 'action',
            'request_params': {
                'module': _mod,
                'command': _cmd,
                'command_params': params
            }
        }
        try:
            raw_data = json.dumps(req_data).encode('utf8')
            self._socket.send(raw_data)
            response = self._socket.recv()

            data = json.loads(response.decode())
            if 'hijack' in data.keys():
                data['socket'] = self._socket
            response = data
        except FileNotFoundError:
            response = {'error': "can't connect to service"}
        except OSError as err:
            response = {'error': str(err)}
        except json.JSONDecodeError:
            response = {'error': "can't parse data from server. Raw response: %s" % response}
        except zmq.error.Again:
            response = {'error': "movai socket got timeout, try increacing timeout"}
        except json.JSONDecodeError:
            response = {'error': "can't parse data from server. Raw response: %s" % response}

        # in case something went wrong, destroy the connection, and next time
        # try again
        finally:
            self.ctx.destroy(1)
        return response


__all__ = ['Sdk']
