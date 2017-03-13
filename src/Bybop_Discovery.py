# This sample uses https://pypi.python.org/pypi/zeroconf as its MDNS implementation

from zeroconf import ServiceBrowser, Zeroconf
import socket
import threading

class DeviceID(object):
    BEBOP_DRONE = '0901'
    JUMPING_SUMO = '0902'
    SKYCONTROLLER = '0903'
    SKYCONTROLLER_2 = '090f'
    JUMPING_NIGHT = '0905'
    JUMPING_RACE = '0906'
    BEBOP_2 = '090c'

    ALL = [ BEBOP_DRONE,
            BEBOP_2,
            JUMPING_SUMO,
            JUMPING_RACE,
            JUMPING_NIGHT,
            SKYCONTROLLER,
            SKYCONTROLLER_2,
        ]

class Discovery(object):
    """
    Basic implementation of a MDNS search for ARSDK Devices.

    The protocol here is not covered by the ARSDK but this implementation is here to provide a fully working
    sample code.
    """
    def __init__(self, deviceId):
        """
        Create and start a researcher for devices on network.

        Arguments:
        - deviceId : List of deviceIds (strings) to search.
        """
        self._zeroconf = Zeroconf()
        self._browser = []
        self._services = {}
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)
        for did in deviceId:
            self._browser.append(ServiceBrowser(self._zeroconf, '_arsdk-' + str(did) + '._udp.local.', self))

    def stop(self):
        """
        Stop searching.

        When stopped, this object can not be restarted
        """
        with self._lock:
            self._cond.notify_all()
        self._zeroconf.close()

    def get_devices(self):
        """ Get the current list of devices """
        return dict(self._services)

    def wait_for_change(self, timeout=None):
        """
        Wait for a change in the device list

        Keyword arguments:
        - timeout : Timeout in floating point seconds for the operation
        """
        with self._lock:
            self._cond.wait(timeout)

    def _signal_change(self):
        with self._lock:
            self._cond.notify_all()

    def remove_service(self, zeroconf, type, name):
        """ Internal function for zeroconf.ServiceBrowser. """
        if name in self._services:
            del self._services[name]
            self._signal_change()

    def add_service(self, zeroconf, type, name):
        """ Internal function for zeroconf.ServiceBrowser. """
        info = zeroconf.get_service_info(type, name)
        if info is not None:
            self._services[name] = info
            self._signal_change()
        else:
            print 'Found a service witout info : ' + name + '. Stopping !'
            self.stop()


def get_name(device):
    """ Get the display name of a device """
    return device.name[0:-(len(device.type) + 1)]

def get_ip(device):
    """ Get the IP, as string, of a device """
    return socket.inet_ntoa(device.address)

def get_port(device):
    """ Get the port, as string, of a device """
    return str(device.port)

def get_device_id(device):
    """ Get the device_id of a device """
    return device.type[len('_arsdk-'):-len('._udp.local.')]
