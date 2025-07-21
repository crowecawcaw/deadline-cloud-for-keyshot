## Adapterless concept

We will do a major refactor on this package.

Current it has two main parts:

- a submitter. a plugin for keyshot which runs in keyshot. it generates a Deadline Cloud job template for the scene and submits it
- an adapter. a python application that runs on workres that actually run the render jobs in Deadline Cloud. the adapter has two parts
  1. one part runs across the entire session. it opens the keyshot scene once then waits to receive render commands.
  2. a part that runs for each task in a session. it sends render commands to the session adapter component.

the adapter adds complexity but givies us:

- scene only has to open once for the session instead of once per task. can save time when rendering many frames/tasks in a session
- detects errors in logs and exists early
- report progress based on incoming logs

currently the adapter is structured as an independent python application that's intalled on the worker separately. the separate applciation
is painful to test, manage, distribute, and update. I want to replace it with python scripts that are embedded directly in the job template
so the adapter/scripts dont need to be separately managed.

high level design points:

- there will be two embedded scripts, one that runs over the session and one that runs for each task. just the like the adapter
- our new scripts must support the same high level features as the curent adapter. but we shouldn't mirror its structure which is overly complicated.
- the scripts will by invoked via keyshot's executable by passing in the script path to run. the scripts will run in keyshot's python instance
- the scripst must onyl use the stndard library. we cannot add additional libraries.
- the two scripts will communicate over sockets

next steps:

1. survey current adapter and outline high level features. write them down
2. write up a design doc that outlines the interfaces for the design

## High-Level Features of the Current Adapter

### 1. Session Management

- **Session Initialization**: Opens KeyShot and loads the scene file once per session
- **Session Cleanup**: Properly closes KeyShot when the session ends
- **Error Handling**: Detects and reports errors during session initialization

### 2. Rendering Capabilities

- **Frame Rendering**: Renders specific frames from the scene
- **Output Format Control**: Supports multiple output formats (PNG, JPEG, EXR, TIFF, PSD)
- **Render Options**: Passes render options from the submitter to KeyShot
- **Render Device Selection**: Allows overriding the render device (CPU/GPU)

### 3. Progress Monitoring

- **Progress Tracking**: Parses KeyShot output to track render progress (percentage)
- **Completion Detection**: Detects when rendering is complete
- **Error Detection**: Monitors logs for errors and fails early when errors are detected

### 4. Communication Architecture

- **IPC Mechanism**: Uses a socket-based server/client architecture for communication
- **Action Queue**: Maintains a queue of actions to be performed by KeyShot
- **Regex Handlers**: Uses regex patterns to parse and respond to KeyShot output

### 5. Job Control

- **Cancellation Support**: Handles job cancellation requests
- **Timeout Management**: Implements timeouts for various operations

### 6. Integration with OpenJD

- **Adaptor Runtime Integration**: Implements the OpenJD adaptor interface
- **Schema Validation**: Validates input data against schemas
- **Telemetry**: Records events for monitoring and debugging

### 7. Submitter Features

- **Scene Packaging**: Can package scene and all referenced files into a KSP bundle
- **Job Template Generation**: Creates OpenJD job templates
- **Parameter Management**: Handles various render parameters
- **Settings Persistence**: Saves and loads settings between sessions
- **UI Integration**: Provides dialog interfaces within KeyShot

### 8. File Management

- **Input/Output Path Handling**: Manages file paths for input scenes and output renders
- **Path Mapping**: Handles path mapping between different environments
- **File Bundling**: Packages and unpacks scene files and dependencies

## Key Files for Quick Orientation

### Adapter Components

- `/src/deadline/keyshot_adaptor/KeyShotAdaptor/adaptor.py`: Main adapter implementation that manages the session lifecycle
- `/src/deadline/keyshot_adaptor/KeyShotClient/keyshot_client.py`: Client that runs inside KeyShot and communicates with the adapter
- `/src/deadline/keyshot_adaptor/KeyShotClient/keyshot_handler.py`: Handles KeyShot-specific operations like rendering and scene loading

### Submitter Components

- `/src/deadline/keyshot_submitter/Submit to AWS Deadline Cloud.py`: KeyShot plugin script that creates and submits job templates

### Configuration and Schema Files

- `/src/deadline/keyshot_adaptor/KeyShotAdaptor/schemas/`: JSON schemas for validating input data
- `/src/deadline/keyshot_adaptor/KeyShotAdaptor/KeyShotAdaptor.json`: Adapter configuration

### Project Documentation

- `/README.md`: Main project documentation
- `/ADAPTERLESS.md`: This file, containing the refactoring plan

### Package Structure

- `/src/deadline/keyshot_adaptor/__init__.py`: Package initialization
- `/src/deadline/keyshot_submitter/__init__.py`: Submitter package initialization

## Adapterless Design Document

### Code Organization and Build Process

The final artifact will be a single Python submitter script that runs in KeyShot. For better code organization and testability, the codebase will be structured as separate files:

1. **Submitter Script** (`keyshot_submitter.py`) - The main script that runs in KeyShot
2. **Job Template** (`job_template.py`) - Contains the job template skeleton as a Python dictionary
3. **Session Script** (`session.py`) - The embedded script for session management
4. **Task Script** (`task.py`) - The embedded script for task execution

A build script will combine these components into the final submitter script:

```
+----------------+     +----------------+     +----------------+     +----------------+
|                |     |                |     |                |     |                |
| session.py     |     | task.py        |     | job_template.py|     | keyshot_       |
| (Session       |     | (Task          |     | (Template      |     | submitter.py   |
| Script)        |     | Script)        |     | Skeleton)      |     | (Main Script)  |
|                |     |                |     |                |     |                |
+----------------+     +----------------+     +----------------+     +----------------+
         |                    |                      |                      |
         v                    v                      v                      v
                           +----------------+
                           |                |
                           | build.py       |
                           | (Build Script) |
                           |                |
                           +----------------+
                                   |
                                   v
                           +----------------+
                           |                |
                           | Submit to AWS  |
                           | Deadline Cloud.|
                           | py (Final)     |
                           |                |
                           +----------------+
```

This approach provides several benefits:

1. **Testability**: Each component can be unit tested independently
2. **Readability**: Code is organized in logical, manageable files
3. **Maintainability**: Changes to one component don't require modifying the entire codebase
4. **Development Workflow**: Multiple developers can work on different components simultaneously

The build script will:

1. Read the content of `session.py` and `task.py`
2. Inject them as strings into the appropriate locations in `job_template.py`
3. Combine the populated job template with `keyshot_submitter.py`
4. Output the final "Submit to AWS Deadline Cloud.py" script

### Component Architecture

The new design will consist of two main components:

1. **Session Script** - Runs for the entire session lifecycle
2. **Task Script** - Runs for each individual task/frame

### Overview

The new adapterless design will replace the current adapter architecture with two embedded Python scripts that will be included directly in the job template. This approach eliminates the need for a separately installed adapter application while maintaining all the key functionality of the current system.

### Design Goals

1. Maintain all current functionality including session stickiness
2. Simplify the architecture and reduce complexity
3. Use only standard library components (no external dependencies)
4. Make deployment and updates easier by embedding scripts in job templates
5. Improve testability and maintainability

### Component Architecture

The new design will consist of two main components:

1. **Session Script** - Runs for the entire session lifecycle
2. **Task Script** - Runs for each individual task/frame

#### Communication Between Components

The two scripts will communicate via a simple socket-based IPC mechanism:

```
+----------------+                  +---------------+
|                |                  |               |
| Session Script |<---------------->| Task Script   |
| (session.py)   |   Socket IPC     | (task.py)     |
|                |                  |               |
+----------------+                  +---------------+
       |                                   |
       | Controls KeyShot                  | Sends render commands
       v                                   v
+----------------+
|                |
|    KeyShot     |
|                |
+----------------+
```

### Session Script Interface

The Session Script (`session.py`) will:

1. Start and maintain a TCP socket server on a fixed port
2. Open KeyShot and load the scene file
3. Listen for and process commands from Task Scripts
4. Handle session-level operations and cleanup
5. Listen for SIGTERM signals for graceful shutdown
6. Not interact with logs directly (KeyShot output is redirected to a log file)

```python
class KeyShotSession:
    def __init__(self, ...):
        # Set up signal handlers for SIGTERM
        # Configure fixed port (e.g., 9876)
        # load scene file
        # configure render settings
        pass

    def handle_message(self, message, params):
        # Process commands from Task Scripts
        # Commands include: render_frame, cancel
        # Execute commands in KeyShot
        # Return success/failure over socket
        pass

    def send_message(self, message, params):
        # send a command over the socket. used when a frame is done to send success
        # or when there's a python error to send an error
        pass

    def handle_sigterm(self, signum, frame):
        # Handle SIGTERM signal for graceful shutdown
        # Clean up resources
        # Close KeyShot
        # Close socket server
        pass

def main():
    # parse CLI args for
        # - scene file
        # - output path
        # - output format
        # - render options
        # - override render device
        # - render device
    # init the keyshot session with those options

if __name__ == "__main__":
    main()
```

### Task Script Interface

The Task Script (`task.py`) will:

1. Connect to the Session Script's TCP socket server on the fixed port
2. Send render commands for specific frames
3. Monitor the log file for render progress and errors
4. Report progress and errors to stdout for Deadline Cloud worker
5. Handle connection issues with a simple retry mechanism

```python
# Simplified interface for the Task Script
class KeyShotTask:
    def __init__(self, frame):
        # connect to session over socket
        # set up termination signal listener
        # set up log listening
        # set up socket listening
        pass

    def send_message(self):
        # Connect to the Session Script's TCP socket server
        # Implement retry mechanism (3 attempts with 5-second delays)
        pass

    def handle_cancel(self):
        # when we get a terminal signal, send a cancel command to the session
        pass

    def handle_message(self):
        # when we get a completion or error message from the session socket, finish/fail the task
        pass

    def tail_logs(self):
        # tail logs
        # look for errors and progress updates and report them using OJD's structured messages format
        # print the log lines to stdout so they appear in the job logs
        pass

def main():
    # parse CLI arg for frame number
    # init the task

if __name__ == "__main__":
    main()
```

### Communication Protocol

The communication protocol between the Session and Task scripts will be a simple JSON-based protocol over a TCP socket with a fixed port.

#### Socket Configuration

- **Socket Type**: TCP socket (socket.SOCK_STREAM)
- **Port**: Fixed port (e.g., 9876)
- **Host**: localhost (127.0.0.1)
- **Timeout**: 5 seconds for operations
- **Reconnection**: Simple retry mechanism (3 attempts with 5-second delays)

#### Supported messages

The Session Script will support the following messages from Task Scripts:

1. **`render_frame`**: Renders a specific frame

   ```json
   {
     "messageId": UUID,
     "command": "render_frame",
     "params": {
       "frame": 1,
       "output_path": "/path/to/output.png"
     }
   }
   ```

2. **`cancel`**: Cancels the current render operation
   ```json
   {"messageId": UUID,  "command": "cancel"}
   ```

Responses will be ACK'd by returning:

```json
{"ack": message_id}
```

Session script can these send messages to the task script:

```json
{"messageId": UUID, "status": "SUCCESS"}
```

```json
{"messageId": UUID, "status": "FAIL"}
```

The Session Script will also listen for SIGTERM signals from the operating system to handle graceful shutdown when the job is terminated.

### Error Handling

Error handling will be implemented with a "fail on errors" approach:

1. **No Error Recovery**: If KeyShot crashes or encounters errors, we will not attempt to restart it
2. **Error Detection**:
   - Session Script: Detect KeyShot process termination
   - Task Script: Detect errors in log files using regex patterns
3. **Error Reporting**:
   - Session Script: Send error messages over the socket to Task Script
   - Task Script: Output detailed error information to stdout for job logs
4. **Socket Communication Errors**:
   - Implement timeouts (5 seconds) for socket operations
   - Simple retry mechanism for connection issues (3 attempts with 1-second delays)
   - Clear error messages when timeouts occur
5. **Script Execution Errors**:
   - Try/except blocks with proper error reporting
   - Exit with non-zero status code to signal failure to Deadline Cloud

All errors will be logged to standard output/error streams for capture by the Deadline Cloud worker.

### Progress Reporting

- logs from the session keyshot process will be directed to a file. the task script will tail them and print them to stdout so they appear in the job logs.
- task script will also parse log lines as it tails them with regexes to detect progress updates and errors. progerss updates will be reported using the OpenJobDescription sturctured message format which teh worker can interpret
- the task script knows the render is complete when it receives a SUCCESS status message

### Job Template Changes

The job template will be updated to:

1. Include the embedded Session and Task scripts
2. Update the onEnter action to launch the Session Script with log redirection
3. Update the onRun action to launch the Task Script
4. Update the onExit action to shut down the Session Script

### Limitations and Considerations

1. **Standard Library Only**: All code must use only Python standard library modules which are supported by KeyShot's Python install
2. **Error Handling**: Fail the task on errors. Make sure errors are properly logged for debugging

### Build Process

- Python build script will combine the separate files into the final submitter script
- Build script will read component files, process/escape content, and insert into appropriate locations.
- The specific files in the code will be:
  - session.py - session script
  - task.py - task script
  - submitter.py - containes the keyshot submitter code and the job template skeleton. has a place holder for the job template which build.py fills
  - build.py - combine the various pieces by using string replacement on placeholders like `{TASK.PY}`
    1.  reads and embeds session.py and task.py
    3.  reads submitter.py and embeds the session and task files as embedded files into the job template
    4.  writes out the final submitter to `dist/Submit to AWS Deadline Cloud.py`

## Style

- Do not add code comments. Prefer clear, self-explanatory function and variable names. Longer names are ok if they are clearer
- Do not add doc strings
- Prefer concrete code over extra abstractions
- Prefer larger functions over using small helpers
- Avoid try-except blocks that only log and reraise exceptions. Prefer to let exceptions bubble up.
  Avoid:
  ```python
      try:
          do_something()
      except Exception as e:
          print(f"Error: {e}")
          raise e
  ```
  Prefer:
  ```python
      # may raise an exception
      do_something()
  ```

## Current Implementation File Structure

The current partial implementation of the adapterless approach can be found in the following directories:

### Source Files

- `./src/adapterless/session.py`: The session script that runs for the entire session lifecycle. It starts a socket server, loads the KeyShot scene, and handles rendering commands.
- `./src/adapterless/task.py`: The task script that runs for each individual task/frame. It connects to the session script, sends render commands, and monitors progress.

### Test Files

- `./test/adapterless/test_socket_communication.py`: Original unittest-based tests for the socket communication between session and task scripts.
- `./test/adapterless/test_socket_communication_pytest.py`: Pytest version of the socket communication tests.

### Running the Tests

To run the pytest tests:

```bash
# From the project root directory
python -m pytest ./test/adapterless/test_socket_communication_pytest.py -v
```

The tests verify:
1. Basic communication between session and task scripts
2. Error handling during rendering
3. Progress reporting through log file monitoring

### Future Development

The current implementation is a partial implementation of the adapterless approach. The next steps include:

1. Implementing the build script to combine the session and task scripts into the job template
2. Updating the submitter to use the embedded scripts
3. Adding more comprehensive tests for edge cases and error scenarios
4. Removing the old adapter-based implementation in `./src/deadline` and `./test/unit` and `./test/integ`
