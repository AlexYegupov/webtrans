import asyncio
import os
import cv2
import numpy as np
import json
import uuid
import argparse
from aiohttp import web, WSMsgType
from aiohttp_cors import setup as setup_cors, ResourceOptions
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack, MediaStreamTrack
from av import VideoFrame, AudioFrame

# Store active connections and their user IDs
pcs = {}
websocket_connections = {}

# Store room information
rooms = {}

# Always use a single default room
DEFAULT_ROOM_ID = "main-room"

def get_or_create_room(room_id=None):
    # Ignore the provided room_id and always use the default room
    if DEFAULT_ROOM_ID not in rooms:
        rooms[DEFAULT_ROOM_ID] = {'users': {}}
    return DEFAULT_ROOM_ID

class HeadlessVideoTrack(VideoStreamTrack):
    """A video track that generates a test pattern for headless server mode."""
    def __init__(self):
        super().__init__()
        # Create a simple color test pattern
        height, width = 480, 640
        self.img = np.zeros((height, width, 3), np.uint8)
        
        # Create color gradient background
        for i in range(height):
            for j in range(width):
                self.img[i, j, 0] = 255 * i // height  # Blue gradient
                self.img[i, j, 1] = 255 * j // width    # Green gradient
                self.img[i, j, 2] = 255 * (i + j) // (height + width)  # Red gradient
        
        # Add text to the image
        font = cv2.FONT_HERSHEY_SIMPLEX
        cv2.putText(self.img, 'WebRTC Headless Server', (50, height//2 - 50), 
                    font, 1, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(self.img, 'Running in Headless Mode', (50, height//2), 
                    font, 1, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(self.img, 'Use your browser camera instead', (50, height//2 + 50), 
                    font, 0.8, (255, 255, 255), 2, cv2.LINE_AA)

    async def recv(self):
        pts, time_base = await self.next_timestamp()
        # Create a copy to avoid modifying the original
        frame = self.img.copy()
        
        # Add a moving element to show it's live
        timestamp = int(time.time() * 10) % 100
        cv2.putText(frame, f'Server Time: {timestamp/10:.1f}s', 
                   (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
        
        # Add current date and time
        current_time = time.strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(frame, current_time, 
                   (width - 230, height - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
        
        video_frame = VideoFrame.from_ndarray(frame, format="rgb24")
        video_frame.pts = pts
        video_frame.time_base = time_base
        return video_frame

# We don't need the MicrophoneStreamTrack anymore as we'll use the client's microphone

async def index(request):
    return web.FileResponse(os.path.join("static", "index.html"))

async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    
    # Generate a unique user ID
    user_id = str(uuid.uuid4())
    
    # Get room ID from query parameters or create a new one
    room_id = request.query.get('room', None)
    room_id = get_or_create_room(room_id)
    
    # Store the WebSocket connection
    if room_id not in websocket_connections:
        websocket_connections[room_id] = {}
    websocket_connections[room_id][user_id] = ws
    
    # Add user to room
    rooms[room_id]['users'][user_id] = {
        'username': f'User-{user_id[:5]}',
        'joined_at': asyncio.get_event_loop().time()
    }
    
    # Notify all users in the room about the new user
    await broadcast_room_update(room_id)
    
    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                data = json.loads(msg.data)
                if data['type'] == 'offer':
                    # Forward offer to the target user
                    target_id = data['target']
                    if target_id in websocket_connections.get(room_id, {}):
                        await websocket_connections[room_id][target_id].send_json({
                            'type': 'offer',
                            'offer': data['offer'],
                            'from': user_id
                        })
                elif data['type'] == 'answer':
                    # Forward answer to the target user
                    target_id = data['target']
                    if target_id in websocket_connections.get(room_id, {}):
                        await websocket_connections[room_id][target_id].send_json({
                            'type': 'answer',
                            'answer': data['answer'],
                            'from': user_id
                        })
                elif data['type'] == 'ice_candidate':
                    # Forward ICE candidate to the target user
                    target_id = data['target']
                    if target_id in websocket_connections.get(room_id, {}):
                        await websocket_connections[room_id][target_id].send_json({
                            'type': 'ice_candidate',
                            'candidate': data['candidate'],
                            'from': user_id
                        })
                elif data['type'] == 'get_users':
                    # Send list of users in the room, excluding the current user
                    # This prevents the client from creating a peer connection with itself
                    other_users = [uid for uid in rooms[room_id]['users'].keys() if uid != user_id]
                    await ws.send_json({
                        'type': 'user_list',
                        'users': other_users,
                        'room_id': room_id
                    })
            elif msg.type == WSMsgType.ERROR:
                print(f'WebSocket connection closed with exception {ws.exception()}')
    finally:
        # Clean up when the WebSocket is closed
        if room_id in websocket_connections and user_id in websocket_connections[room_id]:
            del websocket_connections[room_id][user_id]
        if room_id in rooms and user_id in rooms[room_id]['users']:
            del rooms[room_id]['users'][user_id]
            # Remove room if empty
            if not rooms[room_id]['users']:
                del rooms[room_id]
            else:
                # Notify remaining users about the departure
                await broadcast_room_update(room_id)
    
    return ws

async def broadcast_room_update(room_id):
    """Broadcast room user list to all connected clients in the room"""
    if room_id in websocket_connections:
        all_users = list(rooms[room_id]['users'].keys())
        for user_id, ws in websocket_connections[room_id].items():
            try:
                # Exclude the current user from the list sent to them
                other_users = [uid for uid in all_users if uid != user_id]
                await ws.send_json({
                    'type': 'user_list',
                    'users': other_users,
                    'room_id': room_id
                })
            except Exception as e:
                print(f"Error broadcasting to {user_id}: {e}")

async def get_room_info(request):
    """Get information about a specific room"""
    room_id = request.match_info.get('room_id')
    if room_id in rooms:
        return web.json_response({
            'room_id': room_id,
            'user_count': len(rooms[room_id]['users'])
        })
    return web.json_response({'error': 'Room not found'}, status=404)

async def create_room(request):
    """Create a new room and return its ID"""
    room_id = get_or_create_room()
    return web.json_response({'room_id': room_id})

async def on_shutdown(app):
    # Close all WebSocket connections
    for room_id in websocket_connections:
        for user_id, ws in websocket_connections[room_id].items():
            await ws.close()
    
    # Close all peer connections
    for user_id, pc in pcs.items():
        await pc.close()
    
    # Clear all data structures
    websocket_connections.clear()
    pcs.clear()
    rooms.clear()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WebRTC signaling server")
    parser.add_argument("--host", default="0.0.0.0", help="Host for HTTP server (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8081, help="Port for HTTP server (default: 8081)")
    parser.add_argument("--public-host", help="Public host name for WebRTC (for ngrok)")
    args = parser.parse_args()
    
    # If using ngrok, set the public host
    if args.public_host:
        print(f"Using public host: {args.public_host}")
    
    # Create web application
    app = web.Application()
    app.on_shutdown.append(on_shutdown)
    
    # Setup CORS
    cors = setup_cors(app, defaults={
        "*": ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
            allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"]
        )
    })
    
    # Add routes
    app.router.add_get("/", index)
    app.router.add_get("/ws", websocket_handler)
    app.router.add_get("/api/rooms/{room_id}", get_room_info)
    app.router.add_post("/api/rooms", create_room)
    
    # Add static files with CORS
    static_resource = app.router.add_static("/static/", path="static", name="static")
    cors.add(static_resource)
    
    # Run the app
    print(f"Starting server on http://{args.host}:{args.port}")
    web.run_app(app, host=args.host, port=args.port)
