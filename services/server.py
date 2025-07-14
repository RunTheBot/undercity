import pyrealsense2 as rs
import numpy as np
import cv2
import json
import gzip
import asyncio
import websockets
import threading
import time
from typing import Dict, Set

class RealSenseStreamer:
    def __init__(self, host='0.0.0.0', port=8765):
        self.host = host
        self.port = port
        self.clients: Set[websockets.WebSocketServerProtocol] = set()
        self.pipeline = None
        self.align = None
        self.intrinsics = None
        self.streaming = False
        self.lock = threading.Lock()
        
    def setup_realsense(self):
        try:
            self.pipeline = rs.pipeline()
            config = rs.config()
            
            # Enable depth and color streams
            config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
            config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)
            
            # Start pipeline
            profile = self.pipeline.start(config)
            
            # Get intrinsics for point cloud generation
            color_profile = profile.get_stream(rs.stream.color).as_video_stream_profile()
            self.intrinsics = color_profile.get_intrinsics()
            
            # Create align object to align depth frames to color frames
            align_to = rs.stream.color
            self.align = rs.align(align_to)
            
            print("RealSense camera initialized successfully")
            return True
            
        except Exception as e:
            print(f"Failed to initialize RealSense: {e}")
            return False
    
    def generate_point_cloud(self, depth_frame, color_frame):
        """Generate point cloud from depth and color frames"""
        try:
            # Convert frames to numpy arrays
            depth_image = np.asanyarray(depth_frame.get_data())
            color_image = np.asanyarray(color_frame.get_data())
            
            # Convert BGR to RGB
            color_image = cv2.cvtColor(color_image, cv2.COLOR_BGR2RGB)
            
            # Create point cloud data
            height, width = depth_image.shape
            points = []
            colors = []
            
            # Get depth scale
            depth_scale = depth_frame.get_units()
            
            # Generate 3D points
            for y in range(0, height, 2):  # Sample every 2nd pixel for performance
                for x in range(0, width, 2):
                    depth = depth_image[y, x]
                    if depth > 0:
                        # Convert depth to meters
                        depth_meters = depth * depth_scale
                        
                        # Convert pixel coordinates to 3D coordinates
                        pixel_x = x
                        pixel_y = y
                        
                        # Use intrinsics to convert to 3D
                        fx = self.intrinsics.fx
                        fy = self.intrinsics.fy
                        ppx = self.intrinsics.ppx
                        ppy = self.intrinsics.ppy
                        
                        # Calculate 3D coordinates
                        z = depth_meters
                        x_3d = (pixel_x - ppx) * z / fx
                        y_3d = (pixel_y - ppy) * z / fy
                        
                        # Add point and color
                        points.append([x_3d, y_3d, z])
                        colors.append(color_image[y, x].tolist())
            
            return {
                'points': points,
                'colors': colors,
                'timestamp': time.time()
            }
            
        except Exception as e:
            print(f"Error generating point cloud: {e}")
            return None
    
    def compress_point_cloud(self, point_cloud_data):
        """Compress point cloud data using gzip"""
        try:
            # Convert to JSON string
            json_data = json.dumps(point_cloud_data)
            
            # Compress with gzip
            compressed_data = gzip.compress(json_data.encode('utf-8'))
            
            return compressed_data
            
        except Exception as e:
            print(f"Error compressing point cloud: {e}")
            return None
    
    async def stream_to_clients(self):
        if not self.pipeline:
            print("RealSense pipeline not initialized")
            return
        
        self.streaming = True
        print("Starting point cloud streaming...")
        
        try:
            while self.streaming:
                # Wait for frames
                frames = self.pipeline.wait_for_frames()
                frames = self.align.process(frames)
                
                depth_frame = frames.get_depth_frame()
                color_frame = frames.get_color_frame()
                
                if not depth_frame or not color_frame:
                    print("No depth or color frame received")
                    continue
                
                # Generate point cloud
                point_cloud_data = self.generate_point_cloud(depth_frame, color_frame)
                
                if point_cloud_data:
                    # Compress data
                    compressed_data = self.compress_point_cloud(point_cloud_data)
                    
                    if compressed_data:
                        # Send to all connected clients
                        with self.lock:
                            disconnected_clients = set()
                            for client in self.clients:
                                try:
                                    await client.send(compressed_data)
                                except websockets.exceptions.ConnectionClosed:
                                    disconnected_clients.add(client)
                                except Exception as e:
                                    print(f"Error sending to client: {e}")
                                    disconnected_clients.add(client)
                            
                            # Remove disconnected clients
                            self.clients -= disconnected_clients
                            if disconnected_clients:
                                print(f"Removed {len(disconnected_clients)} disconnected clients. Active clients: {len(self.clients)}")
                
                # Control frame rate
                await asyncio.sleep(0.033)  # ~30 FPS
                
        except Exception as e:
            print(f"Error in streaming loop: {e}")
        finally:
            self.streaming = False
    
    async def handle_client(self, websocket):
        client_id = id(websocket)
        print(f"New client: {client_id}")
        
        with self.lock:
            self.clients.add(websocket)
        
        try:
            welcome_msg = {
                'type': 'welcome',
                'message': 'hi',
                'client_id': client_id
            }
            await websocket.send(json.dumps(welcome_msg))
            
            # Keep connection alive and handle client messages
            async for message in websocket:
                try:
                    data = json.loads(message)
                    if data.get('type') == 'ping':
                        await websocket.send(json.dumps({'type': 'pong'}))
                except json.JSONDecodeError:
                    print(f"Invalid JSON from client {client_id}")
                except Exception as e:
                    print(f"Error handling client message: {e}")
                    
        except websockets.exceptions.ConnectionClosed:
            print(f"Client {client_id} disconnected normally")
        except Exception as e:
            print(f"Error with client {client_id}: {e}")
        finally:
            with self.lock:
                self.clients.discard(websocket)
            print(f"Client {client_id} removed. Active clients: {len(self.clients)}")
    
    async def start_server(self):
        if not self.setup_realsense():
            print("Failed to initialize RealSense camera")
            return
        
        streaming_task = asyncio.create_task(self.stream_to_clients())
        
        server = await websockets.serve(
            self.handle_client,
            self.host,
            self.port
        )
        
        print(f"WebSocket server started on ws://{self.host}:{self.port}")
        
        try:
            await asyncio.gather(
                streaming_task,
                server.wait_closed()
            )
        except KeyboardInterrupt:
            print("bye")
        finally:
            self.streaming = False
            if self.pipeline:
                self.pipeline.stop()
            print("Server stopped")

def main():
    streamer = RealSenseStreamer()
    
    try:
        asyncio.run(streamer.start_server())
    except KeyboardInterrupt:
        print("Server interrupted by user")
    except Exception as e:
        print(f"Server error: {e}")

if __name__ == "__main__":
    main()
