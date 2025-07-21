import os
import sys
import time
import threading
import json
import socket
import tempfile
import pytest
from unittest.mock import MagicMock, patch
import uuid

# Create a mock lux module
class MockLux:
    RENDER_OUTPUT_PNG = "png"
    RENDER_OUTPUT_JPEG = "jpeg"
    RENDER_ENGINE_PRODUCT = 0
    RENDER_ENGINE_INTERIOR = 1
    RENDER_ENGINE_PRODUCT_GPU = 3
    RENDER_ENGINE_INTERIOR_GPU = 4
    
    def __init__(self):
        self.current_engine = self.RENDER_ENGINE_PRODUCT
        self.current_frame = 1
        self.render_in_progress = False
    
    def openFile(self, path):
        print(f"Mock: Opening file {path}")
        return True
    
    def renderImage(self, path, opts=None, format=None):
        print(f"Mock: Rendering to {path} with format {format}")
        self.render_in_progress = True
        
        # Start a thread to simulate rendering progress
        def render_progress():
            for i in range(0, 101, 20):
                if not self.render_in_progress:
                    break
                print(f"Rendering: {i}%")
                time.sleep(0.2)
            if self.render_in_progress:
                print("Finished Rendering")
                self.render_in_progress = False
        
        threading.Thread(target=render_progress, daemon=True).start()
        return True
    
    def getKeyShotDisplayVersion(self):
        return (12, 0)
    
    def getRenderEngine(self):
        return self.current_engine
    
    def setRenderEngine(self, engine):
        print(f"Mock: Setting render engine to {engine}")
        self.current_engine = engine
        return True
    
    def setAnimationFrame(self, frame):
        print(f"Mock: Setting animation frame to {frame}")
        self.current_frame = frame
        return True
    
    def getRenderOptions(self):
        return MockRenderOptions()
    
    def pause(self):
        print("Mock: KeyShot paused")

class MockRenderOptions:
    def __init__(self, dict=None):
        self.options = dict or {}
    
    def setAddToQueue(self, value):
        self.options["addToQueue"] = value

# Mock the lux module
sys.modules['lux'] = MockLux()

# Import the modules from the src directory
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'src'))
from adapterless.session import KeyShotSession
from adapterless.task import KeyShotTask

# Patch the session.py file's initialize_keyshot method to skip file existence check
@pytest.fixture
def patch_initialize_keyshot():
    original_initialize_keyshot = KeyShotSession.initialize_keyshot
    
    def patched_initialize_keyshot(self):
        try:
            # Skip file existence check
            print(f"Mock: Opening scene file: {self.scene_file}")
            
            # Set output format
            mock_lux = sys.modules['lux']  # Get the mock lux module
            try:
                self.output_format_code = getattr(mock_lux, self.output_format)
            except AttributeError:
                raise RuntimeError(f"The output format {self.output_format} is not valid")
            
            # Get current render device
            self.current_device = self.get_current_render_device()
            
            # Handle render device override if needed
            if self.override_render_device and self.render_device:
                self.original_render_device = self.current_device
                if self.render_device != self.current_device:
                    self.set_render_device(self.render_device)
                    self.current_device = self.get_current_render_device()
            
            # Print initialization info
            major_version, minor_version = mock_lux.getKeyShotDisplayVersion()
            print(f"KeyShotClient: KeyShot Version {major_version}.{minor_version}.0")
            print(f"Scene loaded: {self.scene_file}")
            print(f"Output format: {self.output_format}")
            print(f"Render device: {self.current_device}")
            
        except Exception as e:
            print(f"Error initializing KeyShot: {e}")
            # Don't exit, just raise the exception for the test to handle
            raise
    
    # Apply the patch
    KeyShotSession.initialize_keyshot = patched_initialize_keyshot
    
    yield
    
    # Restore the original method
    KeyShotSession.initialize_keyshot = original_initialize_keyshot

# Patch sys.exit to prevent tests from exiting
@pytest.fixture
def patch_sys_exit():
    original_exit = sys.exit
    
    def patched_exit(code=0):
        raise Exception(f"sys.exit({code}) was called")
    
    sys.exit = patched_exit
    
    yield
    
    # Restore the original function
    sys.exit = original_exit

@pytest.fixture
def test_environment():
    # Create a temporary directory for test files
    temp_dir = tempfile.mkdtemp()
    
    # Set up test parameters
    port1 = 9879  # Use different ports for each test
    port2 = 9880
    scene_file = os.path.join(temp_dir, "test.bip")
    output_file_path = os.path.join(temp_dir, "test_%d.png")
    output_format = "RENDER_OUTPUT_PNG"
    frame = 1
    
    # Create a dummy scene file
    with open(scene_file, 'w') as f:
        f.write("Dummy KeyShot scene file")
    
    # Create a temporary log file
    log_file = os.path.join(temp_dir, "test_keyshot.log")
    with open(log_file, 'w') as f:
        f.write("KeyShot log initialized\n")
    
    yield {
        'temp_dir': temp_dir,
        'port1': port1,
        'port2': port2,
        'scene_file': scene_file,
        'output_file_path': output_file_path,
        'output_format': output_format,
        'frame': frame,
        'log_file': log_file
    }
    
    # Clean up temporary files
    if os.path.exists(log_file):
        os.remove(log_file)
    if os.path.exists(scene_file):
        os.remove(scene_file)
    os.rmdir(temp_dir)

@pytest.mark.usefixtures("patch_initialize_keyshot", "patch_sys_exit")
def test_session_task_communication(test_environment):
    # Start the session in a thread
    session = KeyShotSession(
        scene_file=test_environment['scene_file'],
        output_file_path=test_environment['output_file_path'],
        output_format=test_environment['output_format'],
        port=test_environment['port1']
    )
    
    session_thread = threading.Thread(target=session.run)
    session_thread.daemon = True
    session_thread.start()
    
    # Give the session time to start
    time.sleep(1)
    
    # Create and run the task
    task = KeyShotTask(
        frame=test_environment['frame'],
        port=test_environment['port1'],
        log_file=test_environment['log_file']
    )
    
    # Patch the task's handle_message method to prevent sys.exit calls
    original_handle_message = task.handle_message
    def patched_handle_message(message):
        try:
            # Handle acknowledgment
            if "ack" in message and message["ack"] == task.message_id:
                print(f"Command acknowledged by session server")
            
            # Handle success/failure
            if "status" in message:
                status = message["status"]
                
                if status == "SUCCESS":
                    print("Render completed successfully")
                    task.running = False
                    # Don't call sys.exit(0)
                
                elif status == "FAIL":
                    error = message.get("error", "Unknown error")
                    print(f"Render failed: {error}")
                    task.running = False
                    # Don't call sys.exit(1)
        except Exception as e:
            print(f"Error handling message: {e}")
    
    task.handle_message = patched_handle_message
    
    # Start the task in a thread
    task_thread = threading.Thread(target=task.render_frame)
    task_thread.daemon = True
    task_thread.start()
    
    # Simulate log file updates
    with open(test_environment['log_file'], 'a') as f:
        f.write("Starting render\n")
        f.flush()
        time.sleep(0.5)
        
        f.write("Rendering: 25%\n")
        f.flush()
        time.sleep(0.5)
        
        f.write("Rendering: 50%\n")
        f.flush()
        time.sleep(0.5)
        
        f.write("Rendering: 75%\n")
        f.flush()
        time.sleep(0.5)
        
        f.write("Finished Rendering test_1.png\n")
        f.flush()
    
    # Wait for threads to complete (with timeout)
    task_thread.join(timeout=5)
    
    # Stop the session
    session.running = False
    session_thread.join(timeout=5)
    
    # Verify the session and task completed successfully
    assert not session.is_rendering
    
    # Restore the original method
    task.handle_message = original_handle_message

@pytest.mark.usefixtures("patch_initialize_keyshot", "patch_sys_exit")
def test_session_task_error_handling(test_environment):
    # Start the session in a thread
    session = KeyShotSession(
        scene_file=test_environment['scene_file'],
        output_file_path=test_environment['output_file_path'],
        output_format=test_environment['output_format'],
        port=test_environment['port2']  # Use a different port
    )
    
    # Patch the render_frame method to simulate an error
    original_render_frame = session.render_frame
    def mock_render_frame(frame, client_socket=None):
        # Simulate an error during rendering
        if client_socket:
            session.send_message(client_socket, {"status": "FAIL", "error": "Mock rendering error"})
    
    session.render_frame = mock_render_frame
    
    session_thread = threading.Thread(target=session.run)
    session_thread.daemon = True
    session_thread.start()
    
    # Give the session time to start
    time.sleep(1)
    
    # Create the task
    task = KeyShotTask(
        frame=test_environment['frame'],
        port=test_environment['port2'],  # Use the same port as the session
        log_file=test_environment['log_file']
    )
    
    # Patch the task's handle_message method to prevent sys.exit calls
    original_handle_message = task.handle_message
    def patched_handle_message(message):
        try:
            # Handle acknowledgment
            if "ack" in message and message["ack"] == task.message_id:
                print(f"Command acknowledged by session server")
            
            # Handle success/failure
            if "status" in message:
                status = message["status"]
                
                if status == "SUCCESS":
                    print("Render completed successfully")
                    task.running = False
                    # Don't call sys.exit(0)
                
                elif status == "FAIL":
                    error = message.get("error", "Unknown error")
                    print(f"Render failed: {error}")
                    task.running = False
                    # Don't call sys.exit(1)
        except Exception as e:
            print(f"Error handling message: {e}")
    
    task.handle_message = patched_handle_message
    
    # Capture task output to check for error messages
    task_output = []
    original_print = print
    def mock_print(*args, **kwargs):
        message = " ".join(str(arg) for arg in args)
        task_output.append(message)
        original_print(*args, **kwargs)
    
    # Start the task with mocked print
    with patch('builtins.print', mock_print):
        try:
            task.render_frame()
        except Exception as e:
            print(f"Caught exception: {e}")
    
    # Stop the session
    session.running = False
    session_thread.join(timeout=5)
    
    # Verify error handling
    error_messages = [msg for msg in task_output if "error" in msg.lower() or "fail" in msg.lower()]
    assert any("Mock rendering error" in msg for msg in error_messages), f"Error message not found in output: {task_output}"
    
    # Restore the original methods
    session.render_frame = original_render_frame
    task.handle_message = original_handle_message
