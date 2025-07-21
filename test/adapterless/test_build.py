import os
import tempfile
import pytest
import sys

# Add the src directory to the path so we can import the build module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src', 'adapterless'))

from build import build_submitter, escape_python_string, read_file, write_file

class TestBuild:
    
    def test_escape_python_string(self):
        """Test that Python strings are properly escaped for embedding."""
        # Test basic string
        assert escape_python_string("hello") == "hello"
        
        # Test quotes
        assert escape_python_string('say "hello"') == 'say \\"hello\\"'
        assert escape_python_string("say 'hello'") == "say \\'hello\\'"
        
        # Test newlines and tabs
        assert escape_python_string("line1\nline2") == "line1\\nline2"
        assert escape_python_string("tab\there") == "tab\\there"
        
        # Test backslashes
        assert escape_python_string("path\\to\\file") == "path\\\\to\\\\file"
        
        # Test complex string with multiple special characters
        complex_str = 'print("Hello\nWorld")\t# Comment'
        expected = 'print(\\"Hello\\nWorld\\")\\t# Comment'
        assert escape_python_string(complex_str) == expected

    def test_build_submitter_creates_valid_output(self):
        """Test that build_submitter creates a file with all expected components."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create temporary source files
            session_content = '''import lux
print("Session script running")
def main():
    print("Session main function")
'''
            
            task_content = '''import sys
print("Task script running")  
def main():
    print("Task main function")
'''
            
            submitter_content = '''# Submitter script
SESSION_SCRIPT = "REPLACE_WITH_SESSION_SCRIPT"
TASK_SCRIPT = "REPLACE_WITH_TASK_SCRIPT"

def main():
    print("Submitter main")
    print(SESSION_SCRIPT)
    print(TASK_SCRIPT)
'''
            
            # Write temporary files
            session_path = os.path.join(temp_dir, 'session.py')
            task_path = os.path.join(temp_dir, 'task.py')
            submitter_path = os.path.join(temp_dir, 'submitter.py')
            
            write_file(session_path, session_content)
            write_file(task_path, task_content)
            write_file(submitter_path, submitter_content)
            
            # Mock the script directory to point to our temp directory
            import build
            original_file = build.__file__
            build.__file__ = os.path.join(temp_dir, 'build.py')
            
            try:
                output_path = build_submitter()
                
                # Verify the output file was created
                assert os.path.exists(output_path)
                
                # Read the output file
                output_content = read_file(output_path)
                
                # Verify that placeholders were replaced
                assert "REPLACE_WITH_SESSION_SCRIPT" not in output_content
                assert "REPLACE_WITH_TASK_SCRIPT" not in output_content
                
                # Verify that the session and task scripts are embedded
                assert "import lux" in output_content
                assert "Session script running" in output_content
                assert "Task script running" in output_content
                
                # Verify that the scripts are properly escaped
                assert 'SESSION_SCRIPT = "import lux\\nprint(\\"Session script running\\")' in output_content
                assert 'TASK_SCRIPT = "import sys\\nprint(\\"Task script running\\")' in output_content
                
                # Verify the submitter structure is preserved
                assert "def main():" in output_content
                assert "Submitter main" in output_content
                
            finally:
                # Restore the original __file__
                build.__file__ = original_file

    def test_build_with_actual_source_files(self):
        """Test build with the actual session.py and task.py files."""
        # Get the actual source directory
        script_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'src', 'adapterless')
        session_path = os.path.join(script_dir, 'session.py')
        task_path = os.path.join(script_dir, 'task.py')
        submitter_path = os.path.join(script_dir, 'submitter.py')
        
        # Verify source files exist
        assert os.path.exists(session_path), f"Session script not found at {session_path}"
        assert os.path.exists(task_path), f"Task script not found at {task_path}"
        assert os.path.exists(submitter_path), f"Submitter script not found at {submitter_path}"
        
        # Build the submitter
        output_path = build_submitter()
        
        # Verify the output file was created
        assert os.path.exists(output_path)
        
        # Read the output content
        output_content = read_file(output_path)
        
        # Verify placeholders were replaced
        assert "REPLACE_WITH_SESSION_SCRIPT" not in output_content
        assert "REPLACE_WITH_TASK_SCRIPT" not in output_content
        
        # Verify key components from session.py are present
        assert "KeyShotSession" in output_content
        assert "setup_server" in output_content
        
        # Verify key components from task.py are present  
        assert "KeyShotTask" in output_content
        assert "connect_to_session" in output_content
        
        # Verify key components from submitter.py are present
        assert "construct_job_template" in output_content
        assert "def main(" in output_content
        
        # Verify the job template uses embedded scripts
        assert '"name": "sessionScript"' in output_content
        assert '"name": "taskScript"' in output_content
        assert '"data": SESSION_SCRIPT' in output_content
        assert '"data": TASK_SCRIPT' in output_content
        
        print(f"Build test passed! Output file: {output_path}")
        print(f"Output file size: {len(output_content)} characters")
