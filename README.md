# WebRTC Multi-User Chat

This project enables real-time audio/video chat between multiple users using WebRTC technology.

## Features
- Multi-user video and audio streaming via WebRTC
- Room-based chat system
- WebSocket signaling for connection establishment
- Python backend with `aiohttp` and `aiortc`
- Frontend client in vanilla HTML/JS
- Support for local and remote deployment via ngrok

## Requirements
```bash
pip install aiohttp aiortc opencv-python av numpy aiohttp_cors
```

## Run Locally
```bash
python server.py
```

Then open in browser:
```
http://localhost:8081/
```

## Using ngrok for Remote Access

You can use ngrok to make your WebRTC application accessible from the internet. This is useful for testing with users on different networks or when you don't have a public IP address.

### Setup ngrok

1. Install ngrok if you haven't already (https://ngrok.com/download)

2. Start your WebRTC server:
```bash
python server.py
```

3. In a separate terminal, start ngrok:
```bash
ngrok http 8081
```

4. ngrok will display a public URL (e.g., `https://abcd1234.ngrok.io`). Share this URL with others to join your video chat.

### Advanced Configuration

For better performance with ngrok, you can specify the public hostname when starting the server:

```bash
python server.py --public-host=your-ngrok-subdomain.ngrok.io
```

### Limitations

- WebRTC through ngrok may have connectivity issues due to NAT traversal limitations
- For production use, consider using dedicated TURN servers
- The free version of ngrok has session time limits and URL changes between sessions

## Structure
```
project/
├── server.py      # WebRTC signaling server
├── static/
│   └── index.html # Frontend client
└── README.md
```
