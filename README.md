# WebRTC Camera Stream

This project streams your local webcam and (silent) audio to a browser using WebRTC.

## Features
- Live camera streaming via WebRTC
- Dummy audio track (silent)
- Python backend with `aiohttp` and `aiortc`
- Frontend client in vanilla HTML/JS

## Requirements
```bash
pip install aiohttp aiortc opencv-python av numpy
```

## Run
```bash
python server.py
```

Then open in browser:
```
http://localhost:8080/
```

## Structure
```
project/
├── server.py
├── static/
│   └── index.html
└── README.md
