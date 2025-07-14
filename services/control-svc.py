import websockets
import asyncio
import serial
import json

ser = None

async def handle_client(websocket):
    print(f"New client: {websocket.remote_address}")
    
    try:
        async for message in websocket:
            print(f"Received from client: {message}")
            message = message.strip() + '\n'
            if ser:
                try:
                    if (len(message.split(",")) == 2):
                        l, r = message.split(",")
                        l = int(l)
                        r = int(r)
                        print(f"L: {l}, R: {r}")
                        if (l < 5 and l > -5):
                            l = 0
                            print(" -> left joystick error")
                        if (r < 5 and r > -5):
                            r = 0
                            print(" -> right joystick error")
                        message = f"{l},{r}\n"
                        print(f"Message: {message}")
                    ser.write(message.encode('utf-8'))
                    print(f"Forwarded to serial: {message}")
                except Exception as e:
                    print(f"Error writing to serial: {e}")
                    await websocket.send(f"Error: {str(e)}")
            else:
                print("Serial port not available")
                await websocket.send("Error: Serial port not available")
                
    except websockets.exceptions.ConnectionClosed:
        print(f"Client {websocket.remote_address} disconnected")
    except Exception as e:
        print(f"Error handling client {websocket.remote_address}: {e}")

async def start_server():
    server = await websockets.serve(
        handle_client,
        "0.0.0.0",
        6969
    )
    print("WebSocket server started on ws://0.0.0.0:6969")
    print("Waiting for client connections...")
    
    await server.wait_closed()

def setup_serial():
  # /dev/ttyACM1
  global ser
  # Try ACM0 first, then ACM1
  try:
      ser = serial.Serial('/dev/ttyACM0', 115200, timeout=3)
      print("Connected to /dev/ttyACM0")
      return True
  except:
      try:
          ser = serial.Serial('/dev/ttyACM1', 115200, timeout=3) 
          print("Connected to /dev/ttyACM1")
          return True
      except:
          print("Could not connect to either /dev/ttyACM0 or /dev/ttyACM1")
          return False

def main():
    if not setup_serial():
        print("Failed to setup serial connection. Exiting.")
        return
    
    asyncio.run(start_server())

if __name__ == "__main__":
    main()