# PiBorg Gamepad Library

![Polling flowchart](Diagrams/gamepad-logo.svg)

The Gamepad library provides a simple way of getting inputs from joysticks, gamepads, and other game controllers.

Both buttons and axes / joysticks can be referenced by names as well as their raw index numbers.  These can be easily customised and new controllers can easily be added as well.

It is designed and tested for the Raspberry Pi, but it should work with an Linux install and any device which shows up as a ```/dev/input/js?``` device.

Gamepad only uses imports which are part of the standard Python install and works with both Python 2 and 3.

Multiple controllers are also supported, just create more than one ```Gamepad``` instance with different joystick IDs.

See our other projects on GitHub [here](https://github.com/piborg) :)

## Installing the Library

```terminal
pip install git+https://github.com/battisti456/linux-joystick.git
```

That's it. The library does not need installing, it just needs to be downloaded.

## The Gamepad Library

The library provides three basic modes for getting updates from your controller:

1. Polling - we ask the library for the next controller update one at a time.
2. Asynchronous - the controller state is updated in the background.
3. Event - callbacks are made when the controller state changes.

See the examples further down for an explanation of how each mode is used.

The library itself is contained in just two scripts:

### ```Gamepad.py```

The main library, this script contains all of the code which reads input from the controller.  It contains the ```Gamepad``` class which has all of the logic used to decode the joystick events and store the current state.

It works with both the raw axis / joystick and button numbers and easy to read names.  It also contains the threading code needed to handle the background updating used in the asynchronous and event modes.

This script can be run directly using ```./Gamepad.py``` to check your controller mappings are correct or work out the mapping numbers for your own controller.

### ```Controllers.py```

This script contains the layouts for the different controllers.  Each controller is represented by its own class inheriting from the main ```Gamepad``` class.

If the mapping is not right for you the layout for both the axis / joystick names and the button names by editing these classes.  Adding your own controller is also simple, just make your own class based on the example at the bottom :)

Any button or axis without a name can still be used by the raw number if needed.  This also means the ```Gamepad``` class can be used directly if you are only using the raw numbers.

This script is not run directly, instead it is read by ```Gamepad.py``` so that all of the devices are available when Gamepad is imported.
