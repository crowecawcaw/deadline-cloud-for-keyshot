import os
import sys
import time
import threading
import tempfile
import pytest
from unittest.mock import patch
import signal
import platform
import shutil

def find_keyshot_executable() -> str:
    env_path = os.environ.get('KEYSHOT_EXECUTABLE')
    if env_path and os.path.isfile(env_path):
        return env_path
    
    for executable in ['keyshot_headless', 'keyshot']:
        path = shutil.which(executable)
        if path:
            return path
    
    if platform.system() == "Darwin":  # macOS
        default_paths = [
            "/Applications/KeyShot Studio.app/Contents/MacOS/keyshot",
            "/Applications/KeyShot.app/Contents/MacOS/keyshot",
            "/Applications/KeyShot12.app/Contents/MacOS/keyshot",
            "/Applications/KeyShot11.app/Contents/MacOS/keyshot"
        ]
    elif platform.system() == "Windows":
        default_paths = [
            "C:/Program Files/KeyShot/bin/keyshot_headless.exe",
            "C:/Program Files/KeyShot12/bin/keyshot_headless.exe",
            "C:/Program Files/KeyShot11/bin/keyshot_headless.exe",
            os.path.expanduser("~/AppData/Local/KeyShot/bin/keyshot_headless.exe")
        ]
    else:
        default_paths = []
    
    for path in default_paths:
        if os.path.isfile(path):
            return path
        
    raise Exception("KeyShot executable not found. Set the path to the KeyShot executable with the KEYSHOT_EXECUTABLE environment variable.")

# TODO test a render with test_scene.bip
    # start session.py like `keyshot -script session.py` using subprocess
    # start task.py with keyshot as well
    # verify the render completes
