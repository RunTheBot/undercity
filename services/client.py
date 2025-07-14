import asyncio
import websockets
import json
import gzip
import numpy as np
import cv2
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import threading
import time
from typing import Optional, List, Tuple
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PointCloudClient:
    def __init__(self, server_url='ws://localhost:8765'):
        self.server_url = server_url
        self.websocket = None
        self.connected = False
        self.latest_point_cloud = None
        self.lock = threading.Lock()
        self.running = False
        
    async def connect(self):
        try:
            self.websocket = await websockets.connect(self.server_url)
            self.connected = True
            logger.info(f"Connected to server at {self.server_url}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to server: {e}")
            return False
    
    async def receive_messages(self):
        try:
            async for message in self.websocket:
                try:
                    if isinstance(message, str):
                        try:
                            data = json.loads(message)
                            if data.get('type') == 'welcome':
                                logger.info(f"Welcome message: {data.get('message')}")
                            elif data.get('type') == 'pong':
                                logger.debug("Received pong")
                        except json.JSONDecodeError:
                            logger.warning("Received non-JSON string message")
                    else:
                        try:
                            decompressed_data = gzip.decompress(message)
                            point_cloud_data = json.loads(decompressed_data.decode('utf-8'))
                            
                            with self.lock:
                                self.latest_point_cloud = point_cloud_data
                            
                            logger.info(f"Received point cloud with {len(point_cloud_data['points'])} points")
                            
                        except gzip.BadGzipFile:
                            logger.warning("Received binary message that is not gzipped")
                        except Exception as e:
                            logger.error(f"Error processing binary message: {e}")
                        
        except websockets.exceptions.ConnectionClosed:
            logger.info("Connection closed by server")
        except Exception as e:
            logger.error(f"Error receiving messages: {e}")
        finally:
            self.connected = False
    
    def point_cloud_to_depth_image(self, points: List[List[float]], width: int = 640, height: int = 480) -> np.ndarray:
        depth_image = np.zeros((height, width), dtype=np.uint8)
        
        if not points:
            return depth_image
        
        points_array = np.array(points)
        
        x_coords = points_array[:, 0]
        y_coords = points_array[:, 1]
        z_coords = points_array[:, 2]
        
        x_normalized = ((x_coords - x_coords.min()) / (x_coords.max() - x_coords.min()) * (width - 1)).astype(int)
        y_normalized = ((y_coords - y_coords.min()) / (y_coords.max() - y_coords.min()) * (height - 1)).astype(int)
        
        for i in range(len(points)):
            if 0 <= x_normalized[i] < width and 0 <= y_normalized[i] < height:
                depth_value = int((z_coords[i] - z_coords.min()) / (z_coords.max() - z_coords.min()) * 255)
                depth_image[y_normalized[i], x_normalized[i]] = depth_value
        
        return depth_image
    
    def point_cloud_to_color_image(self, points: List[List[float]], colors: List[List[int]], width: int = 640, height: int = 480) -> np.ndarray:
        color_image = np.zeros((height, width, 3), dtype=np.uint8)
        
        if not points or not colors:
            return color_image
        
        points_array = np.array(points)
        colors_array = np.array(colors)
        
        x_coords = points_array[:, 0]
        y_coords = points_array[:, 1]
        
        x_normalized = ((x_coords - x_coords.min()) / (x_coords.max() - x_coords.min()) * (width - 1)).astype(int)
        y_normalized = ((y_coords - y_coords.min()) / (y_coords.max() - y_coords.min()) * (height - 1)).astype(int)
        
        for i in range(len(points)):
            if 0 <= x_normalized[i] < width and 0 <= y_normalized[i] < height:
                color_image[y_normalized[i], x_normalized[i]] = colors_array[i]
        
        return color_image
    
    def create_2d_projection(self, points: List[List[float]], colors: List[List[int]], width: int = 640, height: int = 480) -> Tuple[np.ndarray, np.ndarray]:
        if not points or not colors:
            return np.zeros((height, width), dtype=np.uint8), np.zeros((height, width, 3), dtype=np.uint8)
        
        points_array = np.array(points)
        colors_array = np.array(colors)
        
        x_coords = points_array[:, 0]
        y_coords = points_array[:, 1]
        z_coords = points_array[:, 2]
        
        depth_image = np.zeros((height, width), dtype=np.uint8)
        
        color_image = np.zeros((height, width, 3), dtype=np.uint8)
        
        if len(x_coords) > 0:
            x_normalized = ((x_coords - x_coords.min()) / (x_coords.max() - x_coords.min()) * (width - 1)).astype(int)
            z_normalized = ((z_coords - z_coords.min()) / (z_coords.max() - z_coords.min()) * (height - 1)).astype(int)
            
            for i in range(len(points)):
                if 0 <= x_normalized[i] < width and 0 <= z_normalized[i] < height:
                    depth_value = int((y_coords[i] - y_coords.min()) / (y_coords.max() - y_coords.min()) * 255)
                    depth_image[z_normalized[i], x_normalized[i]] = depth_value
                    color_image[z_normalized[i], x_normalized[i]] = colors_array[i]
        
        return depth_image, color_image
    
    def display_images(self):
        with self.lock:
            if self.latest_point_cloud is None:
                return
            
            points = self.latest_point_cloud['points']
            colors = self.latest_point_cloud['colors']
            
            if not points or not colors:
                return
            
            depth_image, color_image = self.create_2d_projection(points, colors)
            
            cv2.imshow('Point Cloud - Depth View', depth_image)
            cv2.imshow('Point Cloud - Color View', color_image)
            
            side_view = np.zeros((480, 640), dtype=np.uint8)
            if len(points) > 0:
                points_array = np.array(points)
                x_coords = points_array[:, 0]
                y_coords = points_array[:, 1]
                
                x_normalized = ((x_coords - x_coords.min()) / (x_coords.max() - x_coords.min()) * 639).astype(int)
                y_normalized = ((y_coords - y_coords.min()) / (y_coords.max() - y_coords.min()) * 479).astype(int)
                
                for i in range(len(points)):
                    if 0 <= x_normalized[i] < 640 and 0 <= y_normalized[i] < 480:
                        side_view[y_normalized[i], x_normalized[i]] = 255
            
            cv2.imshow('Point Cloud - Side View', side_view)
            
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                self.running = False
    
    async def run(self):
        if not await self.connect():
            return
        
        self.running = True
        
        receive_task = asyncio.create_task(self.receive_messages())
        
        while self.running:
            try:
                self.display_images()
                await asyncio.sleep(0.033)  # ~30 FPS
            except Exception as e:
                logger.error(f"Error in display loop: {e}")
                break
        
        receive_task.cancel()
        if self.websocket:
            await self.websocket.close()
        cv2.destroyAllWindows()
        logger.info("Client stopped")

def main():
    client = PointCloudClient()
    
    try:
        asyncio.run(client.run())
    except KeyboardInterrupt:
        logger.info("Client interrupted by user")
    except Exception as e:
        logger.error(f"Client error: {e}")

if __name__ == "__main__":
    main() 