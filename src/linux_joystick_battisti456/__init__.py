import os

JS_DIR = '/dev/input'
JS_PRE = 'js'

def js_path(joystickNumber:int = 0) -> str:
    return f"{JS_DIR}/{JS_PRE}{joystickNumber}"

def available(joystickNumber:int = 0) -> bool:
    """Check if a joystick is connected and ready to use."""
    return os.path.exists(js_path(joystickNumber))

def all_js_nums() -> set[int]:
    return set(int(item[len(JS_PRE):]) for item in os.listdir(JS_DIR) if item.startswith(JS_PRE))

