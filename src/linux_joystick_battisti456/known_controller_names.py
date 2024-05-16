from .Controllers import *
from . import *

import array

from fcntl import ioctl#type:ignore
from typing import TYPE_CHECKING, IO
if TYPE_CHECKING:
    global iotcl
    def ioctl(fd:IO[bytes],request:int,arg:int|bytes|bytearray|array.array[int]=0,mutate_flag=True):
        ...

known_controller_names:dict[str,type[Gamepad]] = {
    "Core (Plus) Wired Controller" : Gamepad
}

def get_name(num:int):
    """
    open the corresponding input and retrieve its purported name
    
    based on code I found here: https://gist.github.com/rdb/8864666
    """
    with open(js_path(num),'rb') as dev:
        buf = array.array('B', [0] * 64)
        ioctl(dev, 0x80006a13 + (0x10000 * len(buf)), buf) # JSIOCGNAME(len)
        name:str = buf.tobytes().rstrip(b'\x00').decode('utf-8')
    return name

def get_gamepad_type(name:str) -> type[Gamepad]:
    if name in known_controller_names:
        return known_controller_names[name]
    else:
        print(f"WARNING: Gamepad with name '{name}' not known!")
        return Gamepad

def load_controller(num:int) -> Gamepad|None:
    if not js_available(num):
        return None
    name:str = get_name(num)
    gtype = get_gamepad_type(name)
    return gtype(num)
    