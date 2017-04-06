# bybop : Bebop Drone control from python

An alternate implementation of the ARSDK protocols used by the [Parrot Bebop Drone](https://www.parrot.com/us/drones/parrot-bebop-2) and the [Parrot Mini Drones](http://www.parrot.com/usa/products/minidrones/).

This implementation of the SDK is designed to be an example implementation for people willing to use the Parrot products in languages not supported by the [official Parrot SDK](https://github.com/Parrot-Developers/arsdk_manifests).

Prerequisites:

* python 2.7, with threading support

## Status

This project is a work in progress, and thus is not stable, in every possible way:
 * Current error handling is almost non-existant (so most error will lead to a crash)
 * Current API (Bybop_Device) is non-final and will probably change in the future
 
## Installation

This project uses git submodule to include the official Parrot `arsdk-xml` repo. After cloning this repo, you must initialize & update the submodules:
`git submodule init; git submodule update`

## Getting started

This project contains a sample code (samples/interactive.py), which uses `bybop` to find a drone, and to connect to it, then pops an interactive python shell in which you can play with the drone object. You can run this sample with the following command (run inside the samples directory):
`./interactive.py`

### Searching drones on the network

To seach drones on the network, use the `Bybop_Discovery` module:

    from Bybop_Discovery import Discovery, DeviceID
    discovery = Discovery(DeviceID.ALL)

You can specify a sublist of devices to search by providing a list of devices (e.g. `[DeviceID.JUMPING_SUMO, DeviceID.JUMPING_NIGHT, DeviceID.JUMPING_RACE]`) instead of `DeviceID.ALL`.

The discovery module will start searching for devices on the network. You can then retrieve a dictionnary of visible devices (indexed by their name) with:

    devices = discovery.get_devices()

### Connecting to the drone

A convenience function is given in the `Bybop_Device` module:

    from Bybop_Device import create_and_connect
    d2c_port = 54321 # input UDP port
    controller_type = 'Type of Controller'
    controller_name = 'Application Name'
    drone = create_and_connect(some_device, d2c_port, controller_type, controller_name)

This function will return either `None` (error during connection), or a `BebopDrone`, `JumpingSumo`, or `SkyController` instance.

### Disconnecting

Just call:

    drone.stop()
    
The device will automatically disconnect 5 seconds after receiving the last data.

## Interacting with the drone

The `Bybop_Device` module provides the main interface with the device. The `Device` class is device-agnostic and can be used to send/receive generic data. The `BebopDrone` and `JumpingSumo` classes inherit from the `Device` class and add some helpers.

Note: In all further references, commands are spelled in `'project.class.command'` format. For newer commands in features (e.g. the `drone_manager` feature of the SkyController 2) instead of projects, the class argument should be empty (i.e. `'feature..command'` for single args, or `fn(feature, '', command)` for multiple args).

### Reading the state of the device

Every command received is put in a three-level state dictionnary within the `Device` object. To read a specific received command, you can use the following function:

    command_args = drone.get_state(copy=False).get_value('project.class.command')

Where `'project.class.command'` represents the name of the command (i.e. the command `BatteryStateChanged` of class `CommonState` in project `common` is noted `common.CommonState.BatteryStateChanged`).
The `get_value()` function returns either:
* `None` for never received commands
* A dictionnary mapping the arguments names to their values for most commands (i.e. for the `BatteryStateChanged`, the dictionnary will have a format like `{u'percent': 75}`)
* A list of such dictionnaries, for commands declared as `listtype=LIST` in the `libARCommands` xml files. (e.g. the `'ARDrone3.NetworkState.WifiAuthChannelListChanged'` command)
* A dictionnary of such dicitonnaries for commands declared as `listtype=MAP` in the `libARCommands` xml files. In this case, the first argument value will be used as a key to the top-level dictionnary. (e.g. the `'common.CommonState.SensorStatesListChanged'` command)

Some predefined getters might also be defined:

    battery_level = drone.get_battery()

To synchronise your code on a state, you can do the following:

    drone.wait_answer('project.class.command')
    
This function will wait until the given command is received (it has a timeout parameter, defaulting to 5 seconds)
    
### Sending commands

To send a command to the drone, you can either use predefined helpers from the `BebopDrone` or `JumpingSumo` class:

    drone.take_off() # BebopDrone
    drone.jump(0) # JumpingSumo

Or directly send a command by name:

    drone.send_data('ardrone3.Piloting.TakeOff') # Same as drone.take_off()
    drone.send_data('jpsumo.Animations.Jump', 0) # Same as drone.jump(0)

These function will return a `NetworkStatus`, indicating whether the command was properly sent or not.

### Send and wait example

To do a simple 'take off and wait for the drone to be in hovering mode', you can run the following code:

    drone.take_off()
    try:
        flying_state = drone.get_state(copy=False).get_value('ardrone3.PilotingState.FlyingStateChanged')['state']
    except:
        flying_state = None
    while flying_state != 2: # 2 is hovering
        drone.wait_for('ardrone3.PilotingState.FlyingStateChanged')
        try:
            flying_state = drone.get_state(copy=False).get_value('ardrone3.PilotingState.FlyingStateChanged')['state']
        except:
            flying_state = None

## TODO List

No precise order:
 * Include a proper `Ctrl-C` handling during the Discovery and Connection phases
 * Add video streaming support (maybe ... in form of a forked VLC on bebops). Won't come on JumpingSumos !

