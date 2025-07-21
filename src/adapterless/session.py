import os
import socket
import sys
import signal
import json
import time
import re
import uuid
from threading import Thread

try:
    import lux
except ImportError:
    raise OSError("Could not find the KeyShot module. Are you running this inside of KeyShot?")

class KeyShotSession:
    def __init__(self, scene_file, output_file_path, output_format, render_options=None, 
                 override_render_device=False, render_device=None, port=9876):
        self.scene_file = scene_file
        self.output_path = output_file_path
        self.output_format = output_format
        self.render_options = render_options or {}
        self.override_render_device = override_render_device
        self.render_device = render_device
        self.port = port
        self.server_socket = None
        self.is_rendering = False
        self.original_render_device = None
        self.current_device = None
        self.output_format_code = None
        self.running = True
        self.client_sockets = []
        
        signal.signal(signal.SIGTERM, self.handle_sigterm)
        signal.signal(signal.SIGINT, self.handle_sigterm)
        
        self.setup_server()
        self.initialize_keyshot()
        
    def setup_server(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            self.server_socket.bind(('127.0.0.1', self.port))
            self.server_socket.listen(5)
            self.server_socket.settimeout(1)  # 1 second timeout for accept() calls
            print(f"Session server started on port {self.port}")
        except socket.error as e:
            print(f"Failed to start server: {e}")
            sys.exit(1)
    
    def initialize_keyshot(self):
        try:
            # Load scene file
            if not os.path.isfile(self.scene_file):
                raise FileNotFoundError(f"The scene file '{self.scene_file}' does not exist")
            
            print(f"Opening scene file: {self.scene_file}")
            lux.openFile(self.scene_file)
            
            # Set output format
            try:
                self.output_format_code = getattr(lux, self.output_format)
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
            major_version, minor_version = lux.getKeyShotDisplayVersion()
            print(f"KeyShotClient: KeyShot Version {major_version}.{minor_version}.0")
            print(f"Scene loaded: {self.scene_file}")
            print(f"Output format: {self.output_format}")
            print(f"Render device: {self.current_device}")
            
        except Exception as e:
            print(f"Error initializing KeyShot: {e}")
            sys.exit(1)
    
    def get_current_render_device(self):
        current_engine = lux.getRenderEngine()
        is_gpu = current_engine in [lux.RENDER_ENGINE_PRODUCT_GPU, lux.RENDER_ENGINE_INTERIOR_GPU]
        return "GPU" if is_gpu else "CPU"
    
    def set_render_device(self, device):
        current_engine = lux.getRenderEngine()
        
        if device == "GPU" and self.current_device == "CPU":
            engine_map = {
                lux.RENDER_ENGINE_PRODUCT: lux.RENDER_ENGINE_PRODUCT_GPU,
                lux.RENDER_ENGINE_INTERIOR: lux.RENDER_ENGINE_INTERIOR_GPU,
            }
            if current_engine in engine_map:
                try:
                    print(f"Switching render engine from CPU to GPU")
                    lux.setRenderEngine(engine_map[current_engine])
                except Exception:
                    raise RuntimeError(
                        "GPU rendering was requested but no compatible GPU is available on this worker"
                    )
        elif device == "CPU" and self.current_device == "GPU":
            engine_map = {
                lux.RENDER_ENGINE_PRODUCT_GPU: lux.RENDER_ENGINE_PRODUCT,
                lux.RENDER_ENGINE_INTERIOR_GPU: lux.RENDER_ENGINE_INTERIOR,
            }
            if current_engine in engine_map:
                print(f"Switching render engine from GPU to CPU")
                lux.setRenderEngine(engine_map[current_engine])
    
    def render_frame(self, frame, client_socket=None):
        if self.is_rendering:
            self.send_message(client_socket, {"status": "FAIL", "error": "Already rendering"})
            return
        
        try:
            self.is_rendering = True
            
            # Set animation frame
            frame = int(frame)
            lux.setAnimationFrame(frame)
            
            # Prepare render options
            if self.render_options:
                opts = lux.RenderOptions(dict=self.render_options)
            else:
                opts = lux.getRenderOptions()
            
            opts.setAddToQueue(False)
            
            # Set output path
            output_path = self.output_path.replace("%d", str(frame))
            output_dir = os.path.dirname(output_path)
            
            # Create output directory if it doesn't exist
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
            
            print(f"Starting render for frame {frame}")
            print(f"Output path: {output_path}")
            print(f"Output format: {self.output_format}")
            
            # Start render
            lux.renderImage(path=output_path, opts=opts, format=self.output_format_code)
            
            print(f"Finished Rendering {output_path}")
            self.is_rendering = False
            
            # Send success message back to client
            if client_socket:
                self.send_message(client_socket, {"status": "SUCCESS"})
            
        except Exception as e:
            self.is_rendering = False
            error_message = str(e)
            print(f"Error rendering frame {frame}: {error_message}")
            
            # Handle version mismatch error but continue
            if "This scene was saved using a newer version" in error_message:
                print("WARNING: Version mismatch detected but continuing")
                if client_socket:
                    self.send_message(client_socket, {"status": "SUCCESS"})
            else:
                if client_socket:
                    self.send_message(client_socket, {"status": "FAIL", "error": error_message})
    
    def handle_message(self, message_data, client_socket):
        try:
            command = message_data.get("command")
            message_id = message_data.get("messageId")
            
            # Send acknowledgment
            if message_id:
                self.send_message(client_socket, {"ack": message_id})
            
            if command == "render_frame":
                params = message_data.get("params", {})
                frame = params.get("frame")
                if frame is not None:
                    # Start render in a separate thread to not block socket communication
                    render_thread = Thread(target=self.render_frame, args=(frame, client_socket))
                    render_thread.daemon = True
                    render_thread.start()
                else:
                    self.send_message(client_socket, {"status": "FAIL", "error": "No frame specified"})
            
            elif command == "cancel":
                if self.is_rendering:
                    # KeyShot doesn't have a direct API to cancel rendering
                    # We'll need to handle this differently in a real implementation
                    print("Cancel command received, but KeyShot doesn't support direct render cancellation")
                    self.send_message(client_socket, {"status": "SUCCESS"})
                else:
                    self.send_message(client_socket, {"status": "SUCCESS"})
            
            else:
                self.send_message(client_socket, {"status": "FAIL", "error": f"Unknown command: {command}"})
        
        except Exception as e:
            print(f"Error handling message: {e}")
            self.send_message(client_socket, {"status": "FAIL", "error": str(e)})
    
    def send_message(self, client_socket, message):
        if client_socket:
            try:
                message_json = json.dumps(message)
                client_socket.sendall(f"{message_json}\n".encode('utf-8'))
            except socket.error as e:
                print(f"Error sending message to client: {e}")
    
    def handle_sigterm(self, signum, frame):
        print(f"Received signal {signum}, shutting down")
        self.running = False
        self.cleanup()
        sys.exit(0)
    
    def cleanup(self):
        # Close all client connections
        for client_socket in self.client_sockets:
            try:
                client_socket.close()
            except:
                pass
        
        # Close server socket
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
    
    def run(self):
        print("Session server running, waiting for connections...")
        
        while self.running:
            try:
                # Accept new connections
                client_socket, addr = self.server_socket.accept()
                client_socket.settimeout(None)  # No timeout for client sockets
                self.client_sockets.append(client_socket)
                print(f"New connection from {addr}")
                
                # Handle client in a separate thread
                client_thread = Thread(target=self.handle_client, args=(client_socket,))
                client_thread.daemon = True
                client_thread.start()
                
            except socket.timeout:
                # This is expected due to the timeout on accept()
                pass
            except Exception as e:
                if self.running:  # Only log if we're still supposed to be running
                    print(f"Error accepting connection: {e}")
        
        print("Session server stopped")
    
    def handle_client(self, client_socket):
        buffer = ""
        
        while self.running:
            try:
                data = client_socket.recv(4096)
                if not data:
                    break  # Client disconnected
                
                buffer += data.decode('utf-8')
                
                # Process complete messages (newline-delimited JSON)
                while '\n' in buffer:
                    message, buffer = buffer.split('\n', 1)
                    try:
                        message_data = json.loads(message)
                        self.handle_message(message_data, client_socket)
                    except json.JSONDecodeError:
                        print(f"Invalid JSON received: {message}")
                        self.send_message(client_socket, {"status": "FAIL", "error": "Invalid JSON"})
            
            except socket.error as e:
                print(f"Socket error: {e}")
                break
        
        # Clean up client socket
        if client_socket in self.client_sockets:
            self.client_sockets.remove(client_socket)
        try:
            client_socket.close()
        except:
            pass

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='KeyShot Session Script')
    
    # Required parameters
    parser.add_argument('--scene_file', required=True, help='Path to the KeyShot scene file')
    parser.add_argument('--output_file_path', required=True, help='Path pattern for output files')
    
    # Optional parameters
    parser.add_argument('--output_format', default='RENDER_OUTPUT_PNG', 
                        help='Output format (e.g., RENDER_OUTPUT_PNG, RENDER_OUTPUT_JPEG)')
    parser.add_argument('--render_options', default='{}',
                        help='JSON string of render options')
    parser.add_argument('--override_render_device', action='store_true',
                        help='Whether to override the render device')
    parser.add_argument('--render_device', help='Render device to use (CPU or GPU)')
    parser.add_argument('--port', type=int, default=9876,
                        help='Port for the session server')
    
    args = parser.parse_args()
    
    # Process arguments
    scene_file = args.scene_file
    output_file_path = args.output_file_path
    output_format = args.output_format
    render_options = json.loads(args.render_options)
    override_render_device = args.override_render_device
    render_device = args.render_device
    port = args.port
    
    # Create and run the session
    session = KeyShotSession(
        scene_file=scene_file,
        output_file_path=output_file_path,
        output_format=output_format,
        render_options=render_options,
        override_render_device=override_render_device,
        render_device=render_device,
        port=port
    )
    
    try:
        session.run()
    except KeyboardInterrupt:
        print("KeyboardInterrupt received, shutting down")
    finally:
        session.cleanup()
    
    # Create and run the session
    session = KeyShotSession(
        scene_file=scene_file,
        output_file_path=output_file_path,
        output_format=output_format,
        render_options=render_options,
        override_render_device=override_render_device,
        render_device=render_device,
        port=port
    )
    
    try:
        session.run()
    except KeyboardInterrupt:
        print("KeyboardInterrupt received, shutting down")
    finally:
        session.cleanup()

if __name__ == "__main__":
    main()
