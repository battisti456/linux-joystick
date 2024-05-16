from .Controllers import *

known_controller_names:dict[str,type[Gamepad.Gamepad]] = {
    "Core (Plus) Wired Controller" : Gamepad.Gamepad
}