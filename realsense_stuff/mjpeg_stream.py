import pyrealsense2 as rs
import numpy as np
import cv2
import os
import json
import threading
import time
from flask import Flask, Response, render_template_string

# Create a directory to store the frames
if not os.path.exists("temp_frames"):
    os.makedirs("temp_frames")
if not os.path.exists("temp_frames/rgb"):
    os.makedirs("temp_frames/rgb")
if not os.path.exists("temp_frames/depth"):
    os.makedirs("temp_frames/depth")

# Global variables for streaming
app = Flask(__name__)
latest_frame = None
frame_lock = threading.Lock()
capturing = False
frame_count = 0

# RealSense pipeline setup
pipeline = rs.pipeline()
config = rs.config()
config.enable_stream(rs.stream.color, 1280, 720, rs.format.bgr8, 30)
profile = pipeline.start(config)

# Get intrinsics
intrinsics = profile.get_stream(rs.stream.color).as_video_stream_profile().get_intrinsics()

# Calculate and display FOV information
width, height = 1280, 720
fov_x = 2 * np.arctan(width / (2 * intrinsics.fx)) * 180 / np.pi
fov_y = 2 * np.arctan(height / (2 * intrinsics.fy)) * 180 / np.pi

print(f"Camera Intrinsics:")
print(f"  fx: {intrinsics.fx:.2f}, fy: {intrinsics.fy:.2f}")
print(f"  cx: {intrinsics.ppx:.2f}, cy: {intrinsics.ppy:.2f}")
print(f"  FOV X: {fov_x:.2f}°, FOV Y: {fov_y:.2f}°")
print(f"  Resolution: {width}x{height}")

# Save intrinsics as a numpy array
intrinsic_matrix = np.array([
    [intrinsics.fx, 0, intrinsics.ppx],
    [0, intrinsics.fy, intrinsics.ppy],
    [0, 0, 1]
])

align_to = rs.stream.color

def generate_frames():
    global latest_frame, capturing, frame_count
    
    try:
        while True:
            frames = pipeline.wait_for_frames()
            
            color_frame = frames.get_color_frame()
            if not color_frame:
                print("No color frame received.")
                continue
            
            # Convert image to numpy array
            color_image = np.asanyarray(color_frame.get_data())
            
            # Add text overlays
            status = "ON" if capturing else "OFF"
            # cv2.putText(color_image, f"Capture Mode: {status}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            # cv2.putText(color_image, f"Frames saved: {frame_count}", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            # cv2.putText(color_image, f"FOV: {fov_x:.1f}° x {fov_y:.1f}°", (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            
            # Update the latest frame for streaming
            with frame_lock:
                latest_frame = color_image.copy()
                
            time.sleep(0.033)  # ~30 FPS
            
    except Exception as e:
        print(f"Error in frame generation: {e}")
    finally:
        pipeline.stop()

def encode_frame(frame):
    """Encode frame as JPEG"""
    if frame is None:
        return None
    
    # Encode frame as JPEG
    ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ret:
        return None
    
    return buffer.tobytes()

def generate_mjpeg():
    """Generate MJPEG stream"""
    while True:
        with frame_lock:
            frame = latest_frame
        
        if frame is not None:
            jpeg_frame = encode_frame(frame)
            if jpeg_frame:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + jpeg_frame + b'\r\n')
        
        time.sleep(0.033)  # ~30 FPS

# HTML template for the web interface
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>RealSense MJPEG Stream</title>
    <style>
        body { 
            font-family: Arial, sans-serif; 
            text-align: center; 
            background-color: #f0f0f0;
            margin: 0;
            padding: 20px;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        h1 { color: #333; }
        .stream-container {
            margin: 20px 0;
            border: 2px solid #333;
            display: inline-block;
        }
        .controls {
            margin: 20px 0;
        }
        button {
            background-color: #4CAF50;
            color: white;
            padding: 10px 20px;
            margin: 0 10px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 16px;
        }
        button:hover {
            background-color: #45a049;
        }
        .info {
            background-color: white;
            padding: 15px;
            margin: 20px 0;
            border-radius: 5px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>RealSense MJPEG Stream</h1>        <div class="info">
            <p>RGB camera feed from Intel RealSense</p>
            <p>Stream URL: <code>{{ request.url }}video_feed</code></p>
        </div>
        <div class="stream-container">
            <img src="{{ url_for('video_feed') }}" alt="RealSense Stream">
        </div>
        <div class="controls">
            <button onclick="toggleCapture()">Toggle Capture Mode</button>
            <button onclick="saveFrame()">Save Frame</button>
            <button onclick="location.reload()">Refresh</button>
        </div>
    </div>

    <script>
        function toggleCapture() {
            fetch('/toggle_capture')
                .then(response => response.json())
                .then(data => {
                    alert('Capture mode: ' + (data.capturing ? 'ON' : 'OFF'));
                });
        }

        function saveFrame() {
            fetch('/save_frame')
                .then(response => response.json())
                .then(data => {
                    alert(data.message);
                });
        }
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/video_feed')
def video_feed():
    return Response(generate_mjpeg(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/toggle_capture')
def toggle_capture():
    global capturing
    capturing = not capturing
    print(f"Capture Mode: {'ON' if capturing else 'OFF'}")
    return {'capturing': capturing}

@app.route('/save_frame')
def save_frame():
    global frame_count, latest_frame
    
    if not capturing:
        return {'message': 'Not in capture mode. Toggle capture mode ON first.'}
    
    with frame_lock:
        if latest_frame is not None:
            # Get current frames from pipeline
            frames = pipeline.wait_for_frames()
            
            color_frame = frames.get_color_frame()
            
            if color_frame:
                color_image = np.asanyarray(color_frame.get_data())
                
                # Save RGB frame only
                cv2.imwrite(f"temp_frames/rgb/{frame_count}.jpg", color_image)
                np.save(f"temp_frames/depth/{frame_count}_intrinsics.npy", intrinsic_matrix)
                
                print(f"Saved frame {frame_count}")
                frame_count += 1
                
                return {'message': f'Saved frame {frame_count-1}'}
    
    return {'message': 'Failed to save frame'}

if __name__ == '__main__':
    # Start the frame generation thread
    frame_thread = threading.Thread(target=generate_frames)
    frame_thread.daemon = True
    frame_thread.start()
    
    print("Starting MJPEG streaming server...")
    print("Open your browser and go to: http://localhost:5000")
    print("Or access the stream directly at: http://localhost:5000/video_feed")
    
    try:
        app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        pipeline.stop()
