#!/usr/bin/env python3

import os
import sys
import json

def escape_python_string(content):
    """
    Escapes a Python string for embedding as a string literal.
    Handles quotes, newlines, and other special characters.
    """
    # Replace backslashes first to avoid double-escaping
    content = content.replace('\\', '\\\\')
    # Replace quotes
    content = content.replace('"', '\\"')
    content = content.replace("'", "\\'")
    # Replace newlines and other control characters
    content = content.replace('\n', '\\n')
    content = content.replace('\r', '\\r')
    content = content.replace('\t', '\\t')
    return content

def read_file(file_path):
    """Read file content and return as string."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        print(f"Error: File not found: {file_path}")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading file {file_path}: {e}")
        sys.exit(1)

def write_file(file_path, content):
    """Write content to file."""
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
    except Exception as e:
        print(f"Error writing file {file_path}: {e}")
        sys.exit(1)

def build_submitter():
    """
    Build the final submitter script by combining session.py, task.py, and submitter.py.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Input file paths
    session_path = os.path.join(script_dir, 'session.py')
    task_path = os.path.join(script_dir, 'task.py')
    submitter_path = os.path.join(script_dir, 'submitter.py')
    
    # Output file path
    dist_dir = os.path.join(os.path.dirname(script_dir), '..', 'dist')
    output_path = os.path.join(dist_dir, 'Submit to AWS Deadline Cloud.py')
    
    print(f"Reading session script from: {session_path}")
    session_content = read_file(session_path)
    
    print(f"Reading task script from: {task_path}")
    task_content = read_file(task_path)
    
    print(f"Reading submitter script from: {submitter_path}")
    submitter_content = read_file(submitter_path)
    
    # Escape the script contents for embedding as string literals
    escaped_session = escape_python_string(session_content)
    escaped_task = escape_python_string(task_content)
    
    # Replace the placeholder strings in the submitter
    final_content = submitter_content.replace(
        'SESSION_SCRIPT = "REPLACE_WITH_SESSION_SCRIPT"',
        f'SESSION_SCRIPT = "{escaped_session}"'
    )
    
    final_content = final_content.replace(
        'TASK_SCRIPT = "REPLACE_WITH_TASK_SCRIPT"',
        f'TASK_SCRIPT = "{escaped_task}"'
    )
    
    print(f"Writing final submitter to: {output_path}")
    write_file(output_path, final_content)
    
    print("Build completed successfully!")
    return output_path

def main():
    """Main entry point for the build script."""
    if len(sys.argv) > 1 and sys.argv[1] in ['-h', '--help']:
        print("Usage: python build.py")
        print("Builds the final KeyShot submitter script by combining session.py, task.py, and submitter.py")
        return
    
    try:
        output_path = build_submitter()
        print(f"Final submitter script created at: {output_path}")
    except Exception as e:
        print(f"Build failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
