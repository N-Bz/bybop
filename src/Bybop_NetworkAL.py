import socket
import struct
import threading

class DataType:
    ACK=1
    DATA=2
    DATA_LOW_LATENCY=3
    DATA_WITH_ACK=4


class NetworkAL(object):
    """
    Alternate implementation of the ARNetworkAL protocol, for Wifi devices.

    This implementations is fully compliant with the protocol, and has no major
    limiations.

    This implementation uses a thread to do background reads from the socket, and
    send data to the application through a listener. This listener must implement a
    'data_received' function, which will receive the following arguments:
    - type : The type of data received (ack, data, low latency, data with ack)
    - buf : The buffer on which this data was retrieved
    - seq : The sequence number of the data
    - recv_data : The actual data, as a packed string (use the struct module to unpack)
    And a 'did_disconnect' function, without arguments, which will be called if the product
    does not send any data on the network (probably because we lost the network link, or
    because the product has run out of battery)
    """

    def __init__(self, ip, c2d_port, d2c_port, listener):
        """
        Create and start a new instance of ARNetworkAL.

        Arguments:
        - ip (string) : The device address
        - c2d_port : The remove reading port
        - d2c_port : The local reading port
        - listener : A listener which will have its data_received function called
                     when a data is received from the network.
        """
        self._ip = ip
        self._c2d_port = int(c2d_port)
        self._d2c_port = int(d2c_port)
        self._listener = listener
        self._alive = False
        self._running = False
        self._thread = None
        self.start()

    def stop(self):
        """
        Stop the current ARNetworkAL instance.

        Once stopped, an instance can be restarded with the start method.
        """
        if self._running:
            self._alive = False
            self._send_sock.close()

    def start(self):
        """
        Start the current ARNetworkAL instance.

        This function has no effect if the instance is already started.
        """
        if self._running:
            return
        self._alive = True
        self._send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._recv_sock.settimeout(5.0)
        self._recv_sock.bind(('0.0.0.0', self._d2c_port))
        self._thread = threading.Thread(target=self._read_loop)
        self._thread.start()
        self._running = True


    def send_data(self, type, buf, seq, data):
        """
        Send the given data to the remote ARNetworkAL.

        This function returns a boolean indicating whether the send worked.
        This boolean is not an acknowlege, just an indicator that the socket
        write did not fail.

        Arguments:
        - type : The type of data (ack, data, low latency, data with ack)
        - buf : The target buffer for the data
        - seq : The sequence number of the data
        - data : The actual data (ususally a string packed with the struct module)
        """
        sock_data = struct.pack('<BBBI', type, buf, seq, len(data) + 7)
        sock_data += data
        try:
            self._send_sock.sendto(sock_data, (self._ip, self._c2d_port))
        except:
            return False
        return True

    def _read_loop(self):
        while self._alive:
            try:
                sock_data, _ = self._recv_sock.recvfrom(66000)
            except Exception as e:
                break

            the_data = sock_data
            while the_data:
                (type, buf, seq, size) = struct.unpack('<BBBI', the_data[0:7])
                recv_data = the_data[7:size]
                self._listener.data_received(type, buf, seq, recv_data)
                the_data = the_data[size:]

        self._recv_sock.close()
        self._listener.did_disconnect()
        self._running = False
