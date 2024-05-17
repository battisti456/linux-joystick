from typing import NewType, Literal,Callable

import struct
import time
import threading

from . import js_path

ButtonID = NewType('ButtonID',int)
ButtonName = NewType('ButtonName',str)
AxisID = NewType('AxisID',int)
AxisName = NewType('AxisName',str)

type InpID = ButtonID|AxisID
type InpName = ButtonName|AxisName
type EventCode = Literal[0x01,0x02,0x81,0x82]

class Gamepad:
    #region constants
    EVENT_CODE_BUTTON = 0x01
    EVENT_CODE_AXIS = 0x02
    EVENT_CODE_INIT_BUTTON = 0x80 | EVENT_CODE_BUTTON
    EVENT_CODE_INIT_AXIS = 0x80 | EVENT_CODE_AXIS
    MIN_AXIS = -32767.0
    MAX_AXIS = +32767.0
    EVENT_BUTTON = 'BUTTON'
    EVENT_AXIS = 'AXIS'
    fullName = 'Generic (numbers only)'
    #endregion
    class UpdateThread(threading.Thread):
        """Thread used to continually run the updateState function on a Gamepad in the background

        One of these is created by the Gamepad startBackgroundUpdates function and closed by stopBackgroundUpdates"""
        def __init__(self, gamepad):
            threading.Thread.__init__(self)
            self.gamepad:Gamepad|None
            if isinstance(gamepad, Gamepad):
                self.gamepad = gamepad
            else:
                raise ValueError('Gamepad update thread was not created with a valid Gamepad object')
            self.running = True

        def run(self):
            try:
                assert not self.gamepad is None
                while self.running:
                    self.gamepad.updateState()
                self.gamepad = None
            except:
                self.running = False
                self.gamepad = None
                raise

    def __init__(self, joystickNumber = 0):
        self.joystickNumber = str(joystickNumber)
        self.joystickPath = js_path(joystickNumber)
        retryCount = 5
        while True:
            try:
                self.joystickFile = open(self.joystickPath, 'rb')
                break
            except IOError as e:
                retryCount -= 1
                if retryCount > 0:
                    time.sleep(0.5)
                else:
                    raise IOError('Could not open gamepad %s: %s' % (self.joystickNumber, str(e)))
        self.eventSize = struct.calcsize('IhBB')
        self.pressedMap:dict[ButtonID,bool] = {}
        self.wasPressedMap:dict[ButtonID,bool] = {}
        self.wasReleasedMap:dict[ButtonID,bool] = {}
        self.axisMap:dict[AxisID,float] = {}
        self.buttonNames:dict[ButtonID,ButtonName] = {}
        self.buttonIndex:dict[ButtonName,ButtonID] = {}
        self.axisNames:dict[AxisID,AxisName] = {}
        self.axisIndex:dict[AxisName,AxisID] = {}
        self.lastTimestamp = 0
        self.updateThread = None
        self.connected = True
        self.pressedEventMap:dict[ButtonID,set[Callable[[],None]]] = {}
        self.releasedEventMap:dict[ButtonID,set[Callable[[],None]]] = {}
        self.changedEventMap:dict[ButtonID,set[Callable[[bool],None]]] = {}
        self.movedEventMap:dict[AxisID,set[Callable[[float],None]]] = {}

    def __del__(self):
        try:
            self.joystickFile.close()
        except AttributeError:
            pass
#region event code
    def _setupReverseMaps(self):
        for index in self.buttonNames:
            self.buttonIndex[self.buttonNames[index]] = index
        for index in self.axisNames:
            self.axisIndex[self.axisNames[index]] = index

    def _getNextEventRaw(self) -> tuple[int,int,EventCode,InpID]:
        """Returns the next raw event from the gamepad.

        The return format is:
            timestamp (ms), value, event type code, axis / button number
        Throws an IOError if the gamepad is disconnected"""
        if self.connected:
            try:
                rawEvent = self.joystickFile.read(self.eventSize)
            except IOError as e:
                self.connected = False
                raise IOError('Gamepad %s disconnected: %s' % (self.joystickNumber, str(e)))
            if rawEvent is None:
                self.connected = False
                raise IOError('Gamepad %s disconnected' % self.joystickNumber)
            else:
                return struct.unpack('IhBB', rawEvent)
        else:
            raise IOError('Gamepad has been disconnected')

    def _rawEventToDescription(self, event):
        """Decodes the raw event from getNextEventRaw into a formatted string."""
        timestamp, value, eventType, index = event
        if eventType == Gamepad.EVENT_CODE_BUTTON:
            if index in self.buttonNames:
                button = self.buttonNames[index]
            else:
                button = str(index)
            if value == 0:
                return '%010u: Button %s released' % (timestamp, button)
            elif value == 1:
                return '%010u: button %s pressed' % (timestamp, button)
            else:
                return '%010u: button %s state %i' % (timestamp, button, value)
        elif eventType == Gamepad.EVENT_CODE_AXIS:
            if index in self.axisNames:
                axis = self.axisNames[index]
            else:
                axis = str(index)
            position = value / Gamepad.MAX_AXIS
            return '%010u: Axis %s at %+06.1f %%' % (timestamp, axis, position * 100)
        elif eventType == Gamepad.EVENT_CODE_INIT_BUTTON:
            if index in self.buttonNames:
                button = self.buttonNames[index]
            else:
                button = str(index)
            if value == 0:
                return '%010u: Button %s initially released' % (timestamp, button)
            elif value == 1:
                return '%010u: button %s initially pressed' % (timestamp, button)
            else:
                return '%010u: button %s initially state %i' % (timestamp, button, value)
        elif eventType == Gamepad.EVENT_CODE_INIT_AXIS:
            if index in self.axisNames:
                axis = self.axisNames[index]
            else:
                axis = str(index)
            position = value / Gamepad.MAX_AXIS
            return '%010u: Axis %s initially at %+06.1f %%' % (timestamp, axis, position * 100)
        else:
            return '%010u: Unknown event %u, Index %u, Value %i' % (timestamp, eventType, index, value)

    def getNextEvent(self, skipInit = True) -> tuple[Literal['BUTTON','AXIS']|None,InpID|AxisName|ButtonName|None,bool|float|None]:
        """Returns the next event from the gamepad.

        The return format is:
            event name, entity name, value

        For button events the event name is BUTTON and value is either True or False.
        For axis events the event name is AXIS and value is between -1.0 and +1.0.

        Names are string based when found in the button / axis decode map.
        When not available the raw index is returned as an integer instead.

        After each call the internal state used by getPressed and getAxis is updated.

        Throws an IOError if the gamepad is disconnected"""
        self.lastTimestamp, value, eventType, index = self._getNextEventRaw()
        skip = False
        eventName = None
        entityName = None
        finalValue = None
        if eventType == Gamepad.EVENT_CODE_BUTTON:
            bindex:ButtonID = index#type: ignore
            eventName = Gamepad.EVENT_BUTTON
            if bindex in self.buttonNames:
                entityName = self.buttonNames[bindex]
            else:
                entityName = bindex
            if value == 0:
                finalValue = False
                self.wasReleasedMap[bindex] = True
                for callback in self.releasedEventMap[bindex]:
                    callback()
            else:
                finalValue = True
                self.wasPressedMap[bindex] = True
                for callback in self.pressedEventMap[bindex]:
                    callback()
            self.pressedMap[bindex] = finalValue
            for callback in self.changedEventMap[bindex]:
                callback(finalValue)
        elif eventType == Gamepad.EVENT_CODE_AXIS:
            aindex:AxisID = index#type:ignore
            eventName = Gamepad.EVENT_AXIS
            if aindex in self.axisNames:
                entityName = self.axisNames[aindex]
            else:
                entityName = index
            finalValue = value / Gamepad.MAX_AXIS
            self.axisMap[aindex] = finalValue
            for callback in self.movedEventMap[aindex]:
                callback(finalValue)
        elif eventType == Gamepad.EVENT_CODE_INIT_BUTTON:
            bindex:ButtonID = index#type: ignore
            eventName = Gamepad.EVENT_BUTTON
            if bindex in self.buttonNames:
                entityName = self.buttonNames[bindex]
            else:
                entityName = bindex
            if value == 0:
                finalValue = False
            else:
                finalValue = True
            self.pressedMap[bindex] = finalValue
            self.wasPressedMap[bindex] = False
            self.wasReleasedMap[bindex] = False
            self.pressedEventMap[bindex] = set()
            self.releasedEventMap[bindex] = set()
            self.changedEventMap[bindex] = set()
            skip = skipInit
        elif eventType == Gamepad.EVENT_CODE_INIT_AXIS:
            aindex:AxisID = index#type:ignore
            eventName = Gamepad.EVENT_AXIS
            if aindex in self.axisNames:
                entityName = self.axisNames[aindex]
            else:
                entityName = index
            finalValue = value / Gamepad.MAX_AXIS
            self.axisMap[aindex] = finalValue
            self.movedEventMap[aindex] = set()
            skip = skipInit
        else:
            skip = True

        if skip:
            return self.getNextEvent()
        else:
            return eventName, entityName, finalValue
#endregion
#region updated code
    def updateState(self):
        """Updates the internal button and axis states with the next pending event.

        This call waits for a new event if there are not any waiting to be processed."""
        self.lastTimestamp, value, eventType, index = self._getNextEventRaw()
        if eventType == Gamepad.EVENT_CODE_BUTTON:
            bindex:ButtonID = index#type:ignore
            if value == 0:
                finalValue = False
                self.wasReleasedMap[bindex] = True
                for callback in self.releasedEventMap[bindex]:
                    callback()
            else:
                finalValue = True
                self.wasPressedMap[bindex] = True
                for callback in self.pressedEventMap[bindex]:
                    callback()
            self.pressedMap[bindex] = finalValue
            for callback in self.changedEventMap[bindex]:
                callback(finalValue)
        elif eventType == Gamepad.EVENT_CODE_AXIS:
            aindex:AxisID = index#type:ignore
            finalValue = value / Gamepad.MAX_AXIS
            self.axisMap[aindex] = finalValue
            for callback in self.movedEventMap[aindex]:
                callback(finalValue)
        elif eventType == Gamepad.EVENT_CODE_INIT_BUTTON:
            bindex:ButtonID = index#type:ignore
            if value == 0:
                finalValue = False
            else:
                finalValue = True
            self.pressedMap[bindex] = finalValue
            self.wasPressedMap[bindex] = False
            self.wasReleasedMap[bindex] = False
            self.pressedEventMap[bindex] = set()
            self.releasedEventMap[bindex] = set()
            self.changedEventMap[bindex] = set()
        elif eventType == Gamepad.EVENT_CODE_INIT_AXIS:
            aindex:AxisID = index#type:ignore
            finalValue = value / Gamepad.MAX_AXIS
            self.axisMap[aindex] = finalValue
            self.movedEventMap[aindex] = set()

    def startBackgroundUpdates(self, waitForReady = True):
        """Starts a background thread which keeps the gamepad state updated automatically.
        This allows for asynchronous gamepad updates and event callback code.

        Do not use with getNextEvent"""
        if self.updateThread is not None:
            if self.updateThread.running:
                raise RuntimeError('Called startBackgroundUpdates when the update thread is already running')
        self.updateThread = Gamepad.UpdateThread(self)
        self.updateThread.start()
        if waitForReady:
            while not self.isReady() and self.connected:
                time.sleep(1.0)

    def stopBackgroundUpdates(self):
        """Stops the background thread which keeps the gamepad state updated automatically.
        This may be called even if the background thread was never started.

        The thread will stop on the next event after this call was made."""
        if self.updateThread is not None:
            self.updateThread.running = False

    def isReady(self) -> bool:
        """Used with updateState to indicate that the gamepad is now ready for use.

        This is usually after the first button press or stick movement."""
        return len(self.axisMap) + len(self.pressedMap) > 1

    def waitReady(self):
        """Convenience function which waits until the isReady call is True."""
        self.updateState()
        while not self.isReady() and self.connected:
            time.sleep(1.0)
            self.updateState()
#endregion
#region button state code
    def getButtonIndex(self, buttonName:ButtonName) -> ButtonID:
        buttonIndex:ButtonID
        try:
            if buttonName in self.buttonIndex:
                buttonIndex = self.buttonIndex[buttonName]
            else:
                buttonIndex = int(buttonName)#type:ignore
            return buttonIndex
        except KeyError:
            raise ValueError('Button %i was not found' % buttonIndex)#type:ignore
        except ValueError:
            raise ValueError('Button name %s was not found' % buttonName)
    def isPressed(self, buttonName:ButtonName) -> bool:
        """Returns the last observed state of a gamepad button specified by name or index.
        True if pressed, False if not pressed.

        Status is updated by getNextEvent calls.

        Throws ValueError if the button name or index cannot be found."""
        return self.pressedMap[self.getButtonIndex(buttonName)]

    def beenPressed(self, buttonName:ButtonName):
        """Returns True if the button specified by name or index has been pressed since the last beenPressed call.
        Used in conjunction with updateState.

        Throws ValueError if the button name or index cannot be found."""
        buttonIndex = self.getButtonIndex(buttonName)
        if self.wasPressedMap[buttonIndex]:
            self.wasPressedMap[buttonIndex] = False
            return True
        else:
            return False

    def beenReleased(self, buttonName):
        """Returns True if the button specified by name or index has been released since the last beenReleased call.
        Used in conjunction with updateState.

        Throws ValueError if the button name or index cannot be found."""
        buttonIndex = self.getButtonIndex(buttonName)
        if self.wasReleasedMap[buttonIndex]:
            self.wasReleasedMap[buttonIndex] = False
            return True
        else:
            return False
#endregion
    def getAxisIndex(self, axisName:AxisName) -> AxisID:
        axisIndex:AxisID
        try:
            if axisName in self.axisIndex:
                axisIndex = self.axisIndex[axisName]
            else:
                axisIndex = int(axisName)#type:ignore
            return axisIndex
        except KeyError:
            raise ValueError('Axis %i was not found' % axisIndex)#type:ignore
        except ValueError:
            raise ValueError('Axis name %s was not found' % axisName)
    def axis(self, axisName:AxisName):
        """Returns the last observed state of a gamepad axis specified by name or index.
        Throws a ValueError if the axis index is unavailable.

        Status is updated by getNextEvent calls.

        Throws ValueError if the button name or index cannot be found."""
        return self.axisMap[self.getAxisIndex(axisName)]

    def availableButtonNames(self):
        """Returns a list of available button names for this gamepad.
        An empty list means that no button mapping has been provided."""
        return self.buttonIndex.keys()

    def availableAxisNames(self):
        """Returns a list of available axis names for this gamepad.
        An empty list means that no axis mapping has been provided."""
        return self.axisIndex.keys()

    def isConnected(self) -> bool:
        """Returns True until reading from the device fails."""
        return self.connected
#region handler code
    def addButtonPressedHandler(self, buttonName:ButtonName, callback:Callable[[],None]):
        """Adds a callback for when a specific button specified by name or index is pressed.
        This callback gets no parameters passed."""
        self.pressedEventMap[self.getButtonIndex(buttonName)].add(callback)

    def removeButtonPressedHandler(self, buttonName:ButtonName, callback:Callable[[],None]):
        """Removes a callback for when a specific button specified by name or index is pressed."""
        self.pressedEventMap[self.getButtonIndex(buttonName)].remove(callback)

    def addButtonReleasedHandler(self, buttonName:ButtonName, callback:Callable[[],None]):
        """Adds a callback for when a specific button specified by name or index is released.
        This callback gets no parameters passed."""
        self.releasedEventMap[self.getButtonIndex(buttonName)].add(callback)

    def removeButtonReleasedHandler(self, buttonName:ButtonName, callback:Callable[[],None]):
        """Removes a callback for when a specific button specified by name or index is released."""
        self.releasedEventMap[self.getButtonIndex(buttonName)].remove(callback)

    def addButtonChangedHandler(self, buttonName:ButtonName, callback:Callable[[bool],None]):
        """Adds a callback for when a specific button specified by name or index changes.
        This callback gets a boolean for the button pressed state."""
        self.changedEventMap[self.getButtonIndex(buttonName)].add(callback)

    def removeButtonChangedHandler(self, buttonName:ButtonName, callback:Callable[[bool],None]):
        """Removes a callback for when a specific button specified by name or index changes."""
        self.changedEventMap[self.getButtonIndex(buttonName)].remove(callback)

    def addAxisMovedHandler(self, axisName:AxisName, callback:Callable[[float],None]):
        """Adds a callback for when a specific axis specified by name or index changes.
        This callback gets the updated position of the axis."""
        self.movedEventMap[self.getAxisIndex(axisName)].add(callback)

    def removeAxisMovedHandler(self, axisName:AxisName, callback:Callable[[float],None]):
        """Removes a callback for when a specific axis specified by name or index changes."""
        self.movedEventMap[self.getAxisIndex(axisName)].remove(callback)

    def removeAllEventHandlers(self):
        """Removes all event handlers from all axes and buttons."""
        for index in self.pressedEventMap.keys():
            self.pressedEventMap[index] = set()
        for index in self.releasedEventMap.keys():
            self.releasedEventMap[index] = set()
        for index in self.changedEventMap.keys():
            self.changedEventMap[index] = set()
        for index in self.movedEventMap.keys():
            self.movedEventMap[index] = set()
#endregion
    def disconnect(self):
        """Cleanly disconnect and remove any threads and event handlers."""
        self.connected = False
        self.removeAllEventHandlers()
        self.stopBackgroundUpdates()
        del self.joystickFile

