import Bybop_NetworkAL
import struct
import threading

class NetworkStatus:
    OK = 0
    ERROR = 1
    TIMEOUT = 2

class Network(object):
    """
    Simple implementation of the ARNetwork protocol.

    This implementation does not support intenal fifos. If multiple threads tries to send data on the
    same buffer at the same time, the actual send order is undefined.

    The 'send_data' call is blocking to allow simpler implementation, but is not doing busy waiting so
    it can be called from a thread without locking the GIL in python implementations that use one.

    This implementation use a listener to warn the application of newly received data. The listener
    should implement a 'data_received' function accepting the following arguments:
    - buf : The buffer on which this data was retrieved
    - recv_data : The actual data, as a packed string (use the struct module to unpack)
    And a 'did_disconnect' function, without arguments, which will be called if the product
    does not send any data on the network (probably because we lost the network link, or
    because the product has run out of battery)
    """

    def __init__(self, ip, c2d_port, d2c_port, send_buffers, recv_buffers, listener):
        """
        Create a new instance of ARNetwork.

        The instance will manage internally its ARNetworkAL backend.

        Arguments:
        - ip (string) : The device address
        - c2d_port : The remove reading port
        - d2c_port : The local reading port
        - send_buffers : List of buffers which should accept data from the application
                       (i.e. which will be given to the send_data function)
        - recv_buffers : List of buffers which should accept incoming data
        """
        self._netal = Bybop_NetworkAL.NetworkAL(ip, c2d_port, d2c_port, self)
        self._listener = listener
        self._send_buffers = list(send_buffers) # The application writed to these (send to network)
        self._recv_buffers = list(recv_buffers) # The application reads from these (read from network)
        self._send_seq = {}
        self._recv_seq = {}
        self._ack_events = {}
        self._ack_seq = {}
        self._buf_locks = {}
        self._ack_events_lock = threading.Lock()

        for sndb in self._send_buffers:
            self._send_seq[sndb] = 0
            self._buf_locks[sndb] = threading.Lock()
            self._ack_events[sndb] = threading.Event()
            self._ack_seq[sndb] = 0
        for rcvb in self._recv_buffers:
            self._recv_seq[rcvb] = 255



    def stop(self):
        """
        Stop the ARNetwork instance.

        This also stops the ARNetworkAL backend.

        This function has no effect on a stopped instance.
        """
        self._netal.stop()

    def restart(self):
        """
        Restart the ARNetwork instance.

        This also restarts the ARNetworkAL backend.

        This function has no effect on a started instance.
        """
        self._netal.start()

    def _get_seq(self, buf):
        if not buf in self._send_seq:
            self._send_seq[buf] = 0
        ret = self._send_seq[buf]
        self._send_seq[buf] += 1
        self._send_seq[buf] %= 256
        return ret

    def send_data(self, buf, data, type, timeout=0.15, tries=5):
        """
        Send some data over the network, and return an ARNetworkStatus.

        The keyword arguments are only used for acknowledged data.
        For other data, the timeout is irrelevant, and only one try will be made.

        For acknowledged data, this function will block until either the acknowledge is received,
        or all the tries have been consumed in timeouts. For other data, this function returns
        almost immediately.

        Arguments:
        - buf : The target buffer for the data (must be part of the send_buffers list given to __init__)
        - data : The data to send
        - type : The type of the data (needs ack or not)

        Keyword arguments:
        - timeout : Timeout in floating point number of seconds, or None if no timeout (default 0.15)
        - tries : Total number of tries before considering a data as lost (default 5)
        """
        if not buf in self._send_buffers:
            return NetworkStatus.ERROR

        seqnum = self._get_seq(buf)
        needack = type == Bybop_NetworkAL.DataType.DATA_WITH_ACK
        status = NetworkStatus.TIMEOUT

        with self._buf_locks[buf]:

            # If we need an ack, clear any pending ack event, and set the requested seqnum
            if needack:
                with self._ack_events_lock:
                    self._ack_events[buf].clear()
                    self._ack_seq[buf] = seqnum

            # Try 'retries' times in case of timeouts
            while tries > 0 and status == NetworkStatus.TIMEOUT:
                tries -= 1

                status = NetworkStatus.OK if self._netal.send_data(type, buf, seqnum, data) else NetworkStatus.ERROR
                # We only set TIMEOUT status for acknowledged data
                if needack and status == NetworkStatus.OK: # Data with ack properly sent
                    status = NetworkStatus.OK if self._ack_events[buf].wait(timeout) else NetworkStatus.TIMEOUT
        return status

    def _send_ack(self, buf, seq):
        answer = struct.pack('<B', seq)
        abuf = buf + 128
        self._netal.send_data(Bybop_NetworkAL.DataType.ACK, abuf, self._get_seq(abuf), answer)

    def _send_pong(self, data):
        self._netal.send_data(Bybop_NetworkAL.DataType.DATA, 1, self._get_seq(1), data)

    def _should_accept(self, buf, seq):
        if not buf in self._recv_seq:
            return False

        prev = self._recv_seq[buf]
        diff = seq - prev
        ok = diff >= 0 or diff <= -10

        if ok:
            self._recv_seq[buf] = seq
        return ok


    def data_received(self, type, buf, seq, recv_data):
        """
        Implementation of the NetworkAL listener.

        This function should not be called direcly by application code !
        """
        if buf == 0: # This is a ping, send a pong !
            self._send_pong(recv_data)

        if type == Bybop_NetworkAL.DataType.ACK:
            ackbuf = buf - 128
            if ackbuf in self._send_buffers:
                seq = struct.unpack('<B', recv_data)[0]
                with self._ack_events_lock:
                    if seq == self._ack_seq[ackbuf]:
                        self._ack_events[ackbuf].set()
        elif type == Bybop_NetworkAL.DataType.DATA:
            self._process_data(buf, seq, recv_data)
        elif type == Bybop_NetworkAL.DataType.DATA_LOW_LATENCY:
            self._process_data(buf, seq, recv_data)
        elif type == Bybop_NetworkAL.DataType.DATA_WITH_ACK:
            self._process_data(buf, seq, recv_data)
            # And send ack !
            self._send_ack(buf, seq)

    def _process_data(self, buf, seq, recv_data):
        if self._should_accept(buf, seq):
            self._listener.data_received(buf, recv_data)

    def did_disconnect(self):
        """
        Implementation of the NetworkAL listener.

        This function should not be called directly by application code !
        """
        self._listener.did_disconnect()
