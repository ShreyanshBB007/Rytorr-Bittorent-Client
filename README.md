# ⚡ RyTorr ⚡

A lightweight BitTorrent client built from scratch in Python with a modern web UI.

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)

## 🎯 Features

- **Complete BitTorrent Protocol Implementation**
  - Bencode encoding/decoding
  - Torrent file parsing (single & multi-file torrents)
  - HTTP, HTTPS, and UDP tracker support
  - Peer wire protocol (handshake, choke/unchoke, interested, bitfield, have, request, piece)
  - SHA-1 piece verification
  - Rarest-first piece selection strategy
  - Endgame mode for faster completion

- **Resume Support**
  - Save and restore download progress
  - Automatic piece verification on resume

- **Modern Web Interface**
  - Real-time progress updates via WebSocket
  - Drag & drop torrent file upload
  - Pause/Resume functionality
  - Peer and file information display
  - Dark theme UI

## 📁 Project Structure

```
rytorr-bittorent-client/
├── bencode.py          # Bencode encoder/decoder
├── torrent_parser.py   # .torrent file parser
├── tracker_client.py   # HTTP/HTTPS/UDP tracker communication
├── peer_connection.py  # Peer handshake and connection
├── peer_messages.py    # BitTorrent protocol messages
├── piece_manager.py    # Piece/block management & verification
├── downloader.py       # Download orchestration & UI integration
├── resume.py           # Progress save/load functionality
├── testing.py          # CLI testing script
├── requirements.txt    # Python dependencies
├── web/
│   ├── app.py          # FastAPI backend with WebSocket
│   ├── static/
│   │   ├── app.js      # Frontend JavaScript
│   │   └── style.css   # UI styles
│   └── templates/
│       └── index.html  # Main HTML page
├── torrents/           # Uploaded .torrent files
└── downloaded-files/   # Downloaded content
```

## 🚀 Getting Started

### Prerequisites

- Python 3.10 or higher
- pip (Python package manager)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/rytorr-bittorent-client.git
   cd rytorr-bittorent-client
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

### Running the Web UI

```bash
cd web
python app.py
```

Then open your browser to **http://localhost:8000**

### Running via CLI (Testing)

```bash
python testing.py path/to/your.torrent
```

## 🔧 Configuration

Environment variables for tuning:

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_ACTIVE_PEERS` | 20 | Maximum concurrent peer connections |
| `TRACKER_TIMEOUT_SECONDS` | 15 | Tracker request timeout |
| `TRACKER_RETRIES` | 2 | Number of tracker retry attempts |
| `TRACKER_VERBOSE` | 1 | Enable tracker logging (0 to disable) |
| `TRACKER_INSECURE_SSL` | 1 | Allow insecure SSL for trackers |

## 📖 How It Works

### 1. Torrent Parsing (`torrent_parser.py`)
Parses `.torrent` files using bencode decoding. Extracts:
- Tracker URLs (announce & announce-list)
- File information (name, size, paths)
- Piece hashes for verification
- Info hash for peer identification

### 2. Tracker Communication (`tracker_client.py`)
Contacts trackers to discover peers:
- **HTTP/HTTPS**: Standard GET request with URL-encoded parameters
- **UDP**: Connection handshake + announce protocol
- Returns list of peer IP:port pairs

### 3. Peer Protocol (`peer_connection.py`, `peer_messages.py`)
Implements the BitTorrent peer wire protocol:
1. **Handshake**: Exchange protocol string, info hash, peer ID
2. **Bitfield**: Peers announce which pieces they have
3. **Interested/Unchoke**: Request permission to download
4. **Request/Piece**: Request and receive 16KB blocks

### 4. Piece Management (`piece_manager.py`)
- Tracks piece availability across peers
- Implements **rarest-first** selection strategy
- Manages block requests within pieces
- Verifies completed pieces with SHA-1

### 5. Download Orchestration (`downloader.py`)
- Coordinates multiple peer connections
- Calculates download speed and ETA
- Handles pause/resume functionality
- Provides state for Web UI updates

## 🖥️ Web UI

The web interface is built with:
- **Backend**: FastAPI with WebSocket support
- **Frontend**: Vanilla JavaScript with modern CSS

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Main UI page |
| POST | `/api/upload` | Upload .torrent file |
| GET | `/api/torrents` | Get all torrent states |
| POST | `/api/torrents/{id}/pause` | Pause a torrent |
| POST | `/api/torrents/{id}/resume` | Resume a torrent |
| DELETE | `/api/torrents/{id}` | Remove a torrent |
| WS | `/ws` | Real-time updates |

## 🧪 Testing

Test with legal torrents like:
- [Big Buck Bunny](https://webtorrent.io/torrents/big-buck-bunny.torrent)
- [Sintel](https://webtorrent.io/torrents/sintel.torrent)

## 🛠️ Technical Details

### Block Size
Standard 16KB (16384 bytes) blocks as per BitTorrent specification.

### Endgame Mode
When only a few blocks remain, duplicate requests are sent to multiple peers to avoid slowdown from a single slow peer.

### Piece Selection
Uses rarest-first algorithm - pieces with fewer available copies are prioritized to maximize swarm health.

## 📝 License

This project is licensed under the MIT License.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## ⚠️ Disclaimer

This software is for educational purposes. Please respect copyright laws and only download content you have the right to access.

---

Built with ❤️ by Shreyansh
