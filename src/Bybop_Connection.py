import json
import sys
import socket

class Connection(object):
    """
    Alternate implementation of the ARDiscovery_Connection protocol.

    This implementation is fully compliant with the protocol in client mode, but
    does not support server mode. Server mode is only used on the products, not on
    the controllers.
    """

    def __init__(self, ip, port):
        """
        Create a new connection object (but does not actually connect)

        Arguments:
        - ip : The device ip address
        - port : The device discovery port
        """
        self._ip = ip
        self._port = int(port)

    def connect(self, d2c_port, controller_type, controller_name, device_id=None):
        """
        Connect to a device.

        Due to the products ARNetworkAL implementation, the connection will only be valid for 5
        seconds if no data is sent, thus an ARNetwork implementation must be started in this time
        frame to keep the connection alive. This is mostly an issue for interactive use.

        Calling this method while a connection is still alive leads to undefined behavior.

        This method blocks until an answer is available from the device. If the device could not be
        contacted, None is returned, else a dictionnary made from the device json answer is returned.
        Application software must check that return_dict['status'] is 0 before using the parameters to
        start an ARNetwork/ARNetworkAL implementation, as a non-zero value means that the connection
        was refused.

        The controller_type/name arguments can be any non-empty string. They are used saved to
        the .pud files, and displayed in the Drone Academy.

        Arguments:
        - d2c_port : The UDP port that will be used locally for reading
        - controller_type : The type of the controller (phone / tablet / pc ...)
        - controllar_name : The name of the controller (application package ...)

        Keyword arguments:
        - device_id : The serial number of the device. When trying to connect to a device, if this
                      field is provided, then the device will only accept the connection if it matches
                      its own serial number. This is typically useful for reconnection after a loss of
                      wifi, when you can not guarantee that the controller is connected to the good
                      network.
        """
        dico = {}
        dico['d2c_port'] = d2c_port
        dico['controller_type'] = controller_type
        dico['controller_name'] = controller_name
        if device_id is not None:
            dico['device_id'] = device_id
        jsonReq = json.dumps(dico, separators=(',', ':'))

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((self._ip, self._port))
            sock.send(jsonReq)
            jsonRet = sock.recv(4096)
            sock.close()
        except socket.error:
            return None

        retDic, _ = json.JSONDecoder().raw_decode(jsonRet)
        return retDic
