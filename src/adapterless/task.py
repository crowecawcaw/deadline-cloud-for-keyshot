import os
import sys
import socket
import json
import time
import re
import signal
import argparse
from threading import Thread

class KeyShotTask:
    def __init__(self, frame, port=9876, log_file=None, max_retries=3, retry_delay=5):
        self.frame = frame
        self.port = port
        self.log_file = log_file
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.socket = None
        self.running = True
        self.message_id = None
        self.log_tail_thread = None
        
        # Set up signal handlers
        signal.signal(signal.SIGTERM, self.handle_cancel)
        signal.signal(signal.SIGINT, self.handle_cancel)
        
        # Connect to session
        self.connect_to_session()
        
        # Start log tailing if log file is provided
        if self.log_file:
            self.log_tail_thread = Thread(target=self.tail_logs)
            self.log_tail_thread.daemon = True
            self.log_tail_thread.start()
    
    def connect_to_session(self):
        retries = 0
        while retries < self.max_retries:
            try:
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket.connect(('127.0.0.1', self.port))
                print(f"Connected to session server on port {self.port}")
                return True
            except socket.error as e:
                retries += 1
                print(f"Connection attempt {retries}/{self.max_retries} failed: {e}")
                if retries < self.max_retries:
                    print(f"Retrying in {self.retry_delay} seconds...")
                    time.sleep(self.retry_delay)
                else:
                    print("Failed to connect to session server after maximum retries")
                    sys.exit(1)
    
    def send_message(self, message):
        if not self.socket:
            print("Not connected to session server")
            return False
        
        try:
            message_json = json.dumps(message)
            self.socket.sendall(f"{message_json}\n".encode('utf-8'))
            return True
        except socket.error as e:
            print(f"Error sending message: {e}")
            return False
    
    def render_frame(self):
        import uuid
        self.message_id = str(uuid.uuid4())
        
        message = {
            "messageId": self.message_id,
            "command": "render_frame",
            "params": {
                "frame": self.frame
            }
        }
        
        if not self.send_message(message):
            print("Failed to send render_frame command")
            sys.exit(1)
        
        # Start listening for responses
        self.listen_for_responses()
    
    def listen_for_responses(self):
        buffer = ""
        
        while self.running:
            try:
                data = self.socket.recv(4096)
                if not data:
                    print("Connection closed by server")
                    sys.exit(1)
                
                buffer += data.decode('utf-8')
                
                # Process complete messages (newline-delimited JSON)
                while '\n' in buffer:
                    message, buffer = buffer.split('\n', 1)
                    try:
                        message_data = json.loads(message)
                        self.handle_message(message_data)
                    except json.JSONDecodeError:
                        print(f"Invalid JSON received: {message}")
            
            except socket.error as e:
                print(f"Socket error: {e}")
                sys.exit(1)
    
    def handle_message(self, message):
        # Handle acknowledgment
        if "ack" in message and message["ack"] == self.message_id:
            print(f"Command acknowledged by session server")
        
        # Handle success/failure
        if "status" in message:
            status = message["status"]
            
            if status == "SUCCESS":
                print("Render completed successfully")
                self.running = False
                sys.exit(0)
            
            elif status == "FAIL":
                error = message.get("error", "Unknown error")
                print(f"Render failed: {error}")
                self.running = False
                sys.exit(1)
    
    def handle_cancel(self, signum=None, frame=None):
        print(f"Received cancellation signal, notifying session server")
        
        # Send cancel command to session
        cancel_message = {
            "messageId": str(uuid.uuid4()),
            "command": "cancel"
        }
        
        self.send_message(cancel_message)
        
        # Give some time for the message to be sent
        time.sleep(1)
        
        # Clean up and exit
        self.cleanup()
        sys.exit(0)
    
    def cleanup(self):
        self.running = False
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
    
    def tail_logs(self):
        if not os.path.exists(self.log_file):
            print(f"Log file {self.log_file} does not exist")
            return
        
        # Regex patterns for progress and errors
        progress_pattern = re.compile(r".*Rendering: ([0-9]+)%.*")
        error_pattern = re.compile(r".*Error: .*|.*\[Error\].*", re.IGNORECASE)
        completion_pattern = re.compile(r".*Finished Rendering.*")
        
        # Open the log file and seek to the end
        with open(self.log_file, 'r') as f:
            f.seek(0, os.SEEK_END)
            
            while self.running:
                line = f.readline()
                if line:
                    # Print the log line to stdout
                    print(line.rstrip())
                    
                    # Check for progress updates
                    progress_match = progress_pattern.match(line)
                    if progress_match:
                        progress = int(progress_match.group(1))
                        self.report_progress(progress)
                    
                    # Check for errors
                    if error_pattern.match(line):
                        print(f"Error detected in logs: {line.strip()}")
                    
                    # Check for completion
                    if completion_pattern.match(line):
                        print("Render completion detected in logs")
                
                else:
                    # No new lines, sleep briefly
                    time.sleep(0.1)
    
    def report_progress(self, progress):
        # Format for OpenJD structured message
        message = {
            "type": "progress",
            "data": {
                "value": progress,
                "maximum": 100
            }
        }
        
        # Print as JSON string with special prefix
        print(f"##openjd-message## {json.dumps(message)}")

def main():
    parser = argparse.ArgumentParser(description='KeyShot Task Script')
    
    # Required parameters
    parser.add_argument('--frame', required=True, type=int, help='Frame number to render')
    
    # Optional parameters
    parser.add_argument('--port', type=int, default=9876, help='Port for the session server')
    parser.add_argument('--log_file', help='Path to the log file to monitor')
    parser.add_argument('--max_retries', type=int, default=3, help='Maximum connection retry attempts')
    parser.add_argument('--retry_delay', type=int, default=5, help='Delay between retry attempts in seconds')
    
    args = parser.parse_args()
    
    # Create and run the task
    task = KeyShotTask(
        frame=args.frame,
        port=args.port,
        log_file=args.log_file,
        max_retries=args.max_retries,
        retry_delay=args.retry_delay
    )
    
    try:
        task.render_frame()
    except KeyboardInterrupt:
        print("KeyboardInterrupt received, cancelling task")
        task.handle_cancel()
    finally:
        task.cleanup()

if __name__ == "__main__":
    main()
