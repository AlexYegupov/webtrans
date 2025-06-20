import asyncio
import os
import cv2
import numpy as np
import json
import uuid
from aiohttp import web, WSMsgType
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack, MediaStreamTrack
from av import VideoFrame, AudioFrame

# Store active connections and their user IDs
pcs = {}
websocket_connections = {}

# Store room information
rooms = {}

# Generate a unique room ID if not provided
def get_or_create_room(room_id=None):
    if room_id is None or room_id not in rooms:
        room_id = str(uuid.uuid4())
        rooms[room_id] = {'users': {}}
    return room_id

class CameraStreamTrack(VideoStreamTrack):
    def __init__(self):
        super().__init__()
        self.cap = cv2.VideoCapture(0)

    async def recv(self):
        pts, time_base = await self.next_timestamp()
        ret, frame = self.cap.read()
        if not ret:
            raise Exception("Не удалось прочитать кадр с камеры")
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
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
                    # Send list of users in the room
                    await ws.send_json({
                        'type': 'user_list',
                        'users': list(rooms[room_id]['users'].keys()),
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
        user_list = list(rooms[room_id]['users'].keys())
        for user_id, ws in websocket_connections[room_id].items():
            try:
                await ws.send_json({
                    'type': 'user_list',
                    'users': user_list,
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

app = web.Application()
app.on_shutdown.append(on_shutdown)
app.router.add_get("/", index)
app.router.add_get("/ws", websocket_handler)
app.router.add_get("/api/rooms/{room_id}", get_room_info)
app.router.add_post("/api/rooms", create_room)
app.router.add_static("/static/", path="static", name="static")

web.run_app(app, port=8081)
