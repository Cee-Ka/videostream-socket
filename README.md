# videostream-socket

Simple RTSP/RTP video streaming demo in Python. A server reads MJPEG frames
from a file and packetizes them into RTP over UDP, while a Tkinter client
controls playback (SETUP/PLAY/PAUSE/TEARDOWN) over RTSP/TCP and renders frames.

## Features
- RTSP control channel (TCP) and RTP media channel (UDP)
- MJPEG file reader with JPEG frame boundaries (FF D8 ... FF D9) for supporting HD
- RTP packetization with marker bit for frame boundaries
- Client-side buffering, basic loss reporting, and session stats

## Requirements
- Python 3.x
- Tkinter
- Pillow: `pip install pillow`

## Project layout
- `python_rtp/Server.py` - RTSP server entry point
- `python_rtp/ServerWorker.py` - RTSP request handling + RTP sender
- `python_rtp/ClientLauncher.py` - client entry point
- `python_rtp/Client.py` - Tkinter GUI + RTP receiver
- `python_rtp/RtpPacket.py` - RTP packet encode/decode
- `python_rtp/VideoStream.py` - MJPEG frame reader
- `python_rtp/sample_1920x1080.mjpeg`, `python_rtp/movie.Mjpeg` - sample videos

## Usage
Start the server (RTSP/TCP):

```bash
python python_rtp/Server.py <server_port>
```

Start the client (RTSP/TCP + RTP/UDP):

```bash
python python_rtp/ClientLauncher.py <server_addr> <server_port> <rtp_port> <video_file>
```

Example (same machine):

```bash
python python_rtp/Server.py 8554
python python_rtp/ClientLauncher.py 127.0.0.1 8554 5004 python_rtp/sample_1920x1080.mjpeg
```

Notes:
- The `video_file` path is sent to the server. It must be valid on the server
  filesystem (absolute or relative to the server working directory).
- The client prints a session report on teardown.
