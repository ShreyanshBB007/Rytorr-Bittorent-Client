import os
import time
import threading
import uuid
import socket
from typing import Dict, List, Optional, Set
from enum import Enum


REQUEST_TIMEOUT_SECONDS = 20
DEFAULT_MAX_ACTIVE_PEERS = 20


# These functions must be defined BEFORE imports to avoid circular import
# (peer_connection.py imports recv_exact from this file)
def recv_exact(sock, n):
    data = b''

    while len(data) < n:
        chunk = sock.recv(n - len(data))

        if not chunk:
            raise ConnectionError("Peer closed connection")

        data += chunk

    return data


def recv_message(sock):
    length_bytes = recv_exact(sock, 4)
    length = int.from_bytes(length_bytes, "big")

    if length == 0:
        return None, None

    message = recv_exact(sock, length)

    msg_id = message[0]
    payload = message[1:]

    return msg_id, payload


# Now safe to import modules that depend on recv_exact
from torrent_parser import Torrent
from tracker_client import TrackerClient
from piece_manager import PieceManager
from peer_connection import handshake_with_peer
from peer_messages import build_interested, build_request, parse_bitfield
from resume import load_progress, save_progress


class TorrentStatus(Enum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    COMPLETED = "completed"
    ERROR = "error"


class TorrentDownloader:
    """
    Lightweight UI wrapper that uses original RyTorr modules directly.
    This class coordinates: torrent_parser, tracker_client, piece_manager, 
    peer_connection, peer_messages, and resume.
    """

    def __init__(self, torrent_path: str, download_dir: str, torrent_id: str = None):
        self.id = torrent_id or str(uuid.uuid4())[:8]
        self.torrent_path = torrent_path
        self.download_dir = download_dir

        # Original modules - YOUR code
        self.torrent: Optional[Torrent] = None
        self.tracker: Optional[TrackerClient] = None
        self.piece_manager: Optional[PieceManager] = None

        # File handling
        self.file_handles: List[tuple] = []
        self.file_lock = threading.Lock()

        # Peer tracking
        self.threads: List[threading.Thread] = []
        self.active_peers: Dict[str, dict] = {}
        self.peers_lock = threading.Lock()

        # State
        self.status = TorrentStatus.QUEUED
        self.error_message = ""
        self.stop_flag = threading.Event()
        self.paused = False

        # Stats
        self.bytes_downloaded = 0
        self.last_speed_time = time.time()
        self.last_bytes = 0
        self.download_speed = 0.0

    def load(self) -> bool:
        """Load torrent using original torrent_parser.py"""
        try:
            self.torrent = Torrent(self.torrent_path)
            self.tracker = TrackerClient(self.torrent)
            self.piece_manager = PieceManager(self.torrent)

            os.makedirs(self.download_dir, exist_ok=True)

            for f in self.torrent.files_info:
                path = os.path.join(self.download_dir, f["path"])
                os.makedirs(os.path.dirname(path), exist_ok=True)
                mode = "r+b" if os.path.exists(path) else "w+b"
                fh = open(path, mode)
                self.file_handles.append((f, fh))

            # Use original resume.py
            load_progress(self.piece_manager, self.torrent, self.file_handles, self.file_lock)

            if self.piece_manager.is_complete():
                self.status = TorrentStatus.COMPLETED

            return True
        except Exception as e:
            self.status = TorrentStatus.ERROR
            self.error_message = str(e)
            return False

    def get_state(self) -> dict:
        """Get current state for UI"""
        if not self.torrent:
            return {
                "id": self.id,
                "name": os.path.basename(self.torrent_path),
                "size": 0,
                "status": self.status.value,
                "progress": 0,
                "download_speed": 0,
                "upload_speed": 0,
                "peers_connected": 0,
                "peers_total": 0,
                "eta_seconds": 0,
                "downloaded_bytes": 0,
                "uploaded_bytes": 0,
                "pieces_completed": 0,
                "pieces_total": 0,
                "files": [],
                "peers": [],
                "error_message": self.error_message,
            }

        pieces_done = len(self.piece_manager.completed_pieces)
        pieces_total = self.piece_manager.total_pieces
        progress = (pieces_done / pieces_total) * 100 if pieces_total > 0 else 0

        downloaded = pieces_done * self.torrent.piece_length
        if pieces_done == pieces_total:
            downloaded = self.torrent.length

        with self.peers_lock:
            peers_list = list(self.active_peers.values())

        files = [{"path": f["path"], "size": f["length"], "progress": progress} 
                 for f in self.torrent.files_info]

        return {
            "id": self.id,
            "name": self.torrent.name,
            "size": self.torrent.length,
            "status": self.status.value,
            "progress": progress,
            "download_speed": self.download_speed,
            "upload_speed": 0,
            "peers_connected": len(peers_list),
            "peers_total": len(peers_list),
            "eta_seconds": int((self.torrent.length - downloaded) / self.download_speed) if self.download_speed > 0 else 0,
            "downloaded_bytes": downloaded,
            "uploaded_bytes": 0,
            "files": files,
            "peers": peers_list,
            "pieces_completed": pieces_done,
            "pieces_total": pieces_total,
            "error_message": self.error_message,
        }

    def update_speed(self):
        """Calculate download speed"""
        now = time.time()
        elapsed = now - self.last_speed_time
        if elapsed >= 1.0:
            delta = self.bytes_downloaded - self.last_bytes
            self.download_speed = delta / elapsed
            self.last_bytes = self.bytes_downloaded
            self.last_speed_time = now

    def start(self) -> bool:
        """Start downloading"""
        if not self.torrent and not self.load():
            return False

        if self.piece_manager.is_complete():
            self.status = TorrentStatus.COMPLETED
            return True

        self.status = TorrentStatus.DOWNLOADING
        self.stop_flag.clear()
        self.paused = False

        thread = threading.Thread(target=self._download_loop, daemon=True)
        thread.start()
        return True

    def _download_loop(self):
        """Main download loop using original tracker_client.py"""
        try:
            self.tracker.verbose_tracker = False
            peers = self.tracker.get_peers()

            if not peers:
                self.status = TorrentStatus.ERROR
                self.error_message = "No peers found"
                return

            max_peers = int(os.getenv("MAX_ACTIVE_PEERS", str(DEFAULT_MAX_ACTIVE_PEERS)))

            for ip, port in peers[:max_peers]:
                if self.stop_flag.is_set():
                    break
                t = threading.Thread(target=self._peer_download, args=(ip, port), daemon=True)
                t.start()
                self.threads.append(t)

            while not self.stop_flag.is_set() and not self.piece_manager.is_complete():
                self.update_speed()
                time.sleep(0.5)

            if self.piece_manager.is_complete():
                self.status = TorrentStatus.COMPLETED

        except Exception as e:
            self.status = TorrentStatus.ERROR
            self.error_message = str(e)

    def _peer_download(self, ip: str, port: int):
        """Download from peer using original peer_connection.py and peer_messages.py"""
        sock = None
        peer_label = f"{ip}:{port}"
        pending = {}
        peer_pieces: Set[int] = set()

        with self.peers_lock:
            self.active_peers[peer_label] = {"ip": ip, "port": port, "pieces_have": 0, "total_pieces": self.piece_manager.total_pieces}

        try:
            # Use original handshake_with_peer from peer_connection.py
            sock = handshake_with_peer(ip, port, self.torrent.info_hash, self.tracker.peer_id)
            if not sock:
                return

            # Use original build_interested from peer_messages.py
            sock.sendall(build_interested())
            sock.settimeout(15)

            peer_choking = True

            while not self.stop_flag.is_set() and not self.piece_manager.is_complete():
                if self.paused:
                    time.sleep(0.5)
                    continue

                try:
                    # Timeout expired requests
                    now = time.time()
                    for key in [k for k, ts in pending.items() if now - ts >= REQUEST_TIMEOUT_SECONDS]:
                        idx, begin = key
                        self.piece_manager.release_block_request(idx, begin)
                        pending.pop(key, None)

                    # Use original recv_message
                    msg_id, payload = recv_message(sock)

                    if msg_id is None:
                        continue
                    elif msg_id == 1:  # Unchoke
                        peer_choking = False
                    elif msg_id == 0:  # Choke
                        peer_choking = True
                    elif msg_id == 5:  # Bitfield - use original parse_bitfield
                        peer_pieces = {p for p in parse_bitfield(payload) if 0 <= p < self.piece_manager.total_pieces}
                        with self.piece_manager.lock:
                            for p in peer_pieces:
                                self.piece_manager.piece_availability[p] += 1
                        with self.peers_lock:
                            if peer_label in self.active_peers:
                                self.active_peers[peer_label]["pieces_have"] = len(peer_pieces)
                    elif msg_id == 4:  # Have
                        if len(payload) >= 4:
                            piece_idx = int.from_bytes(payload[0:4], "big")
                            if 0 <= piece_idx < self.piece_manager.total_pieces and piece_idx not in peer_pieces:
                                peer_pieces.add(piece_idx)
                                with self.piece_manager.lock:
                                    self.piece_manager.piece_availability[piece_idx] += 1
                    elif msg_id == 7:  # Piece
                        idx = int.from_bytes(payload[0:4], "big")
                        begin = int.from_bytes(payload[4:8], "big")
                        block = payload[8:]
                        pending.pop((idx, begin), None)
                        self.bytes_downloaded += len(block)

                        # Use original piece_manager.handle_piece_received
                        completed = self.piece_manager.handle_piece_received(idx, begin, block)
                        if completed is not None:
                            piece_data = self.piece_manager.get_piece_data(completed)
                            self._write_piece(completed, piece_data)
                            save_progress(self.piece_manager)

                    # Request next block using original piece_manager
                    if not peer_choking and peer_pieces:
                        req = self.piece_manager.get_next_block_request_for_peer(peer_pieces)
                        if req:
                            idx, begin, length = req
                            # Use original build_request from peer_messages.py
                            sock.sendall(build_request(idx, begin, length))
                            pending[(idx, begin)] = time.time()
                        else:
                            time.sleep(0.02)

                except socket.timeout:
                    continue
                except Exception:
                    break

        finally:
            for idx, begin in list(pending.keys()):
                self.piece_manager.release_block_request(idx, begin)

            with self.piece_manager.lock:
                for p in peer_pieces:
                    if 0 <= p < self.piece_manager.total_pieces and self.piece_manager.piece_availability[p] > 0:
                        self.piece_manager.piece_availability[p] -= 1

            with self.peers_lock:
                self.active_peers.pop(peer_label, None)

            if sock:
                try:
                    sock.close()
                except:
                    pass

    def _write_piece(self, piece_index: int, piece_data: bytes):
        """Write completed piece to files"""
        global_offset = piece_index * self.torrent.piece_length
        remaining = len(piece_data)
        data_offset = 0

        with self.file_lock:
            for f, fh in self.file_handles:
                file_start = f["offset"]
                file_end = file_start + f["length"]

                if global_offset >= file_end or global_offset < file_start:
                    continue

                write_start = global_offset - file_start
                write_len = min(remaining, file_end - global_offset)

                fh.seek(write_start)
                fh.write(piece_data[data_offset:data_offset + write_len])
                fh.flush()

                remaining -= write_len
                data_offset += write_len
                global_offset += write_len

                if remaining <= 0:
                    break

    def pause(self):
        """Pause download"""
        self.paused = True
        self.status = TorrentStatus.PAUSED

    def resume(self):
        """Resume download"""
        if self.status == TorrentStatus.PAUSED:
            self.paused = False
            self.status = TorrentStatus.DOWNLOADING
            
            # Restart if threads died
            alive = [t for t in self.threads if t.is_alive()]
            if not alive and not self.piece_manager.is_complete():
                self.threads.clear()
                thread = threading.Thread(target=self._download_loop, daemon=True)
                thread.start()

    def stop(self):
        """Stop and cleanup"""
        self.stop_flag.set()
        for t in self.threads:
            t.join(timeout=2)
        for _, fh in self.file_handles:
            try:
                fh.close()
            except:
                pass
        self.file_handles.clear()
        self.threads.clear()


class DownloadManager:
    """Manages multiple torrent downloads for the UI"""

    def __init__(self, download_dir: str = None):
        self.download_dir = download_dir or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "downloaded-files"
        )
        os.makedirs(self.download_dir, exist_ok=True)
        self.torrents: Dict[str, TorrentDownloader] = {}
        self.lock = threading.Lock()

    def add_torrent(self, torrent_path: str, start: bool = True) -> str:
        torrent_id = str(uuid.uuid4())[:8]
        dl = TorrentDownloader(torrent_path, self.download_dir, torrent_id)
        with self.lock:
            self.torrents[torrent_id] = dl
        if start:
            dl.start()
        return torrent_id

    def remove_torrent(self, torrent_id: str, delete_files: bool = False):
        with self.lock:
            if torrent_id in self.torrents:
                dl = self.torrents.pop(torrent_id)
                dl.stop()
                
                # Optionally delete downloaded files
                if delete_files and dl.torrent:
                    for f in dl.torrent.files_info:
                        file_path = os.path.join(dl.download_dir, f["path"])
                        if os.path.exists(file_path):
                            try:
                                os.remove(file_path)
                            except:
                                pass

    def pause_torrent(self, torrent_id: str):
        with self.lock:
            if torrent_id in self.torrents:
                self.torrents[torrent_id].pause()

    def resume_torrent(self, torrent_id: str):
        with self.lock:
            if torrent_id in self.torrents:
                self.torrents[torrent_id].resume()

    def get_all_states(self) -> List[dict]:
        with self.lock:
            return [dl.get_state() for dl in self.torrents.values()]

    def get_global_stats(self) -> dict:
        total_dl = 0.0
        active = 0
        with self.lock:
            for dl in self.torrents.values():
                dl.update_speed()
                total_dl += dl.download_speed
                if dl.status == TorrentStatus.DOWNLOADING:
                    active += 1
        return {
            "total_download_speed": total_dl,
            "total_upload_speed": 0,
            "active_torrents": active,
            "total_torrents": len(self.torrents),
        }

    def shutdown(self):
        with self.lock:
            for dl in self.torrents.values():
                dl.stop()
            self.torrents.clear()