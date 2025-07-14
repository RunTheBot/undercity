import asyncio
import websockets
import json
import gzip
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_client():
    """Simple test client to verify server connection"""
    try:
        async with websockets.connect('ws://localhost:8765') as websocket:
            logger.info("Connected to server")
            
            # Wait for welcome message
            welcome_msg = await websocket.recv()
            logger.info(f"Received: {welcome_msg}")
            
            # Wait for a few point cloud messages
            for i in range(5):
                try:
                    message = await websocket.recv()
                    logger.info(f"Received message type: {type(message)}")
                    
                    if isinstance(message, str):
                        logger.info("Received string message")
                    else:
                        logger.info(f"Received binary message of size: {len(message)} bytes")
                        # Try to decompress
                        try:
                            decompressed = gzip.decompress(message)
                            data = json.loads(decompressed.decode('utf-8'))
                            logger.info(f"Successfully decompressed point cloud with {len(data['points'])} points")
                        except Exception as e:
                            logger.error(f"Failed to decompress: {e}")
                    
                except Exception as e:
                    logger.error(f"Error receiving message: {e}")
                    break
                    
    except Exception as e:
        logger.error(f"Connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_client()) 