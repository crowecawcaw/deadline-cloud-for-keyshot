import os
import sys
import time
import threading
import tempfile
import subprocess
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

@pytest.mark.integration
def test_keyshot_render_integration():
    """Test complete render workflow with KeyShot using test_scene.bip"""
    keyshot_executable = find_keyshot_executable()
    
    # Get absolute paths
    test_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(test_dir))
    scene_file = os.path.join(test_dir, "test_scene.bip")
    session_script = os.path.join(project_root, "src", "adapterless", "session.py")
    task_script = os.path.join(project_root, "src", "adapterless", "task.py")
    
    # Create temporary output directory
    with tempfile.TemporaryDirectory() as temp_dir:
        output_file = os.path.join(temp_dir, "test_render.png")
        log_file = os.path.join(temp_dir, "keyshot.log")
        
        # Verify files exist
        assert os.path.exists(scene_file), f"Scene file not found: {scene_file}"
        assert os.path.exists(session_script), f"Session script not found: {session_script}"
        assert os.path.exists(task_script), f"Task script not found: {task_script}"
        
        # Start session process
        session_cmd = [
            keyshot_executable,
            "-headless",
            "-script", session_script,
            "--scene_file", scene_file,
            "--output_file_path", output_file,
            "--output_format", "RENDER_OUTPUT_PNG",
            "--render_options", "{}",
            "--port", "9876"
        ]
        
        print(f"Starting session with command: {' '.join(session_cmd)}")
        session_process = subprocess.Popen(
            session_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            cwd=temp_dir
        )
        
        # Give session time to start up
        time.sleep(5)
        
        try:
            # Check if session is still running
            if session_process.poll() is not None:
                stdout, _ = session_process.communicate()
                pytest.fail(f"Session process exited early with output: {stdout}")
            
            print("Session process is still running, proceeding with task...")
            
            # Start task process
            task_cmd = [
                keyshot_executable,
                "-headless", 
                "-script", task_script,
                "--frame", "1",
                "--port", "9876",
                "--log_file", log_file
            ]
            
            print(f"Starting task with command: {' '.join(task_cmd)}")
            task_process = subprocess.Popen(
                task_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                cwd=temp_dir
            )
            
            # Wait for task to complete (with longer timeout for rendering)
            try:
                task_stdout, _ = task_process.communicate(timeout=120)  # Increased to 2 minutes
                task_return_code = task_process.returncode
                
                print(f"Task output: {task_stdout}")
                print(f"Task return code: {task_return_code}")
                
                # Task should complete successfully
                assert task_return_code == 0, f"Task failed with return code {task_return_code}"
                
                # Check if output file was created
                assert os.path.exists(output_file), f"Output file not created: {output_file}"
                
                # Verify output file has reasonable size (not empty)
                file_size = os.path.getsize(output_file)
                assert file_size > 1000, f"Output file too small ({file_size} bytes), likely not a valid render"
                
                print(f"Render completed successfully. Output file: {output_file} ({file_size} bytes)")
                
            except subprocess.TimeoutExpired:
                task_process.kill()
                task_stdout, _ = task_process.communicate()
                pytest.fail(f"Task process timed out. Output: {task_stdout}")
                
        finally:
            # Clean up session process and capture its output
            if session_process.poll() is None:
                session_process.terminate()
                try:
                    session_stdout, _ = session_process.communicate(timeout=10)
                    print(f"Session output: {session_stdout}")
                except subprocess.TimeoutExpired:
                    session_process.kill()
                    session_process.wait()
            else:
                # Process already exited, get its output
                session_stdout, _ = session_process.communicate()
                print(f"Session output (already exited): {session_stdout}")


@pytest.mark.integration  
def test_keyshot_render_with_error_handling():
    """Test render workflow with error conditions"""
    keyshot_executable = find_keyshot_executable()
    
    test_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(test_dir))
    session_script = os.path.join(project_root, "src", "adapterless", "session.py")
    task_script = os.path.join(project_root, "src", "adapterless", "task.py")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # Test with non-existent scene file
        fake_scene = os.path.join(temp_dir, "nonexistent.bip")
        output_file = os.path.join(temp_dir, "test_render.png")
        
        session_cmd = [
            keyshot_executable,
            "-headless",
            "-script", session_script,
            "--scene_file", fake_scene,
            "--output_file_path", output_file,
            "--output_format", "RENDER_OUTPUT_PNG",
            "--render_options", "{}",
            "--port", "9877"  # Use different port to avoid conflicts
        ]
        
        session_process = subprocess.Popen(
            session_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            cwd=temp_dir
        )
        
        try:
            # Session should fail or handle the error gracefully
            stdout, _ = session_process.communicate(timeout=30)
            return_code = session_process.returncode
            
            print(f"Session with bad scene file - Return code: {return_code}, Output: {stdout}")
            
            # We expect this to fail in some way (non-zero return code or specific error message)
            # The exact behavior depends on how KeyShot handles missing files
            
        except subprocess.TimeoutExpired:
            session_process.kill()
            session_process.wait()
            pytest.fail("Session process with bad scene file did not exit within timeout")


@pytest.mark.integration
def test_keyshot_socket_communication_only():
    """Test just the socket communication without actual rendering"""
    keyshot_executable = find_keyshot_executable()
    
    # Get absolute paths
    test_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(test_dir))
    scene_file = os.path.join(test_dir, "test_scene.bip")
    session_script = os.path.join(project_root, "src", "adapterless", "session.py")
    task_script = os.path.join(project_root, "src", "adapterless", "task.py")
    
    # Create temporary output directory
    with tempfile.TemporaryDirectory() as temp_dir:
        output_file = os.path.join(temp_dir, "test_render.png")
        log_file = os.path.join(temp_dir, "keyshot.log")
        
        # Start session process
        session_cmd = [
            keyshot_executable,
            "-headless",
            "-script", session_script,
            "--scene_file", scene_file,
            "--output_file_path", output_file,
            "--output_format", "RENDER_OUTPUT_PNG",
            "--render_options", "{}",
            "--port", "9879"  # Use different port
        ]
        
        print(f"Starting session with command: {' '.join(session_cmd)}")
        session_process = subprocess.Popen(
            session_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            cwd=temp_dir
        )
        
        # Give session time to start up
        time.sleep(8)  # Longer startup time
        
        try:
            # Check if session is still running
            if session_process.poll() is not None:
                stdout, _ = session_process.communicate()
                pytest.fail(f"Session process exited early with output: {stdout}")
            
            print("Session process is running, testing socket connection...")
            
            # Test socket connection directly
            import socket
            test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                test_socket.connect(('127.0.0.1', 9879))
                print("✅ Socket connection successful")
                test_socket.close()
            except Exception as e:
                pytest.fail(f"Failed to connect to session socket: {e}")
                
        finally:
            # Clean up session process and capture its output
            if session_process.poll() is None:
                session_process.terminate()
                try:
                    session_stdout, _ = session_process.communicate(timeout=10)
                    print(f"Session output: {session_stdout}")
                except subprocess.TimeoutExpired:
                    session_process.kill()
                    session_process.wait()
            else:
                # Process already exited, get its output
                session_stdout, _ = session_process.communicate()
                print(f"Session output (already exited): {session_stdout}")


    """Test task behavior when session is not running"""
    keyshot_executable = find_keyshot_executable()
    
    test_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(test_dir))
    task_script = os.path.join(project_root, "src", "adapterless", "task.py")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        log_file = os.path.join(temp_dir, "keyshot.log")
        
        task_cmd = [
            keyshot_executable,
            "-headless",
            "-script", task_script, 
            "--frame", "1",
            "--port", "9878",  # Use different port
            "--log_file", log_file
        ]
        
        print(f"Starting task without session: {' '.join(task_cmd)}")
        task_process = subprocess.Popen(
            task_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            cwd=temp_dir
        )
        
        try:
            stdout, _ = task_process.communicate(timeout=30)
            return_code = task_process.returncode
            
            print(f"Task without session - Return code: {return_code}, Output: {stdout}")
            
            # Task should fail when it cannot connect to session
            assert return_code != 0, "Task should fail when session is not running"
            
        except subprocess.TimeoutExpired:
            task_process.kill()
            task_process.wait()
            pytest.fail("Task process without session did not exit within timeout")
