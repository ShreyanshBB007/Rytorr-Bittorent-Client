from torrent_parser import Torrent
from tracker_client import TrackerClient
from peer_connection import handshake_with_peer
from peer_messages import build_interested
from peer_messages import build_piece
from peer_messages import build_request
from downloader import recv_message
from piece_manager import PieceManager
from peer_messages import parse_bitfield
import socket
import os
import threading
import time
from resume import load_progress, save_progress


REQUEST_TIMEOUT_SECONDS = 20
DEFAULT_MAX_ACTIVE_PEERS = 20


def read_block_from_files(piece_index, begin, length, torrent, file_handles):
    global_offset = piece_index * torrent.piece_length + begin

    remaining = length
    chunks = []

    for f, fh in file_handles:
        file_start = f["offset"]
        file_end = file_start + f["length"]

        if global_offset >= file_end:
            continue

        if global_offset < file_start:
            continue

        read_start = global_offset - file_start
        read_len = min(remaining, file_end - global_offset)

        fh.seek(read_start)
        chunks.append(fh.read(read_len))

        remaining -= read_len
        global_offset += read_len

        if remaining <= 0:
            break

    return b"".join(chunks)


def download_from_peer(ip, port, torrent, tracker, piece_manager, file_handles, file_lock):
    sock = None
    peer_label = f"{ip}:{port}"
    pending_requests = {}
    peer_pieces = set()

    try:
        print(f"Connecting to {peer_label}")

        try:
            sock = handshake_with_peer(ip, port, torrent.info_hash, tracker.peer_id)
        except Exception as e:
            print(f"Connection failed for {peer_label}: {e}")
            return

        if not sock:
            print(f"Handshake failed for {peer_label}")
            return

        print(f"Using peer {peer_label}")

        sock.sendall(build_interested())
        print(f"Sent INTERESTED to {peer_label}")
        sock.settimeout(15)

        peer_choking = True

        while not piece_manager.is_complete():
            try:
                now = time.time()
                expired = [
                    key for key, ts in pending_requests.items()
                    if now - ts >= REQUEST_TIMEOUT_SECONDS
                ]

                for index, begin in expired:
                    piece_manager.release_block_request(index, begin)
                    pending_requests.pop((index, begin), None)

                msg_id, payload = recv_message(sock)

                if msg_id is None:
                    continue

                if msg_id == 1:
                    print("Peer unchoked us!")
                    peer_choking = False

                elif msg_id == 0:
                    print("Peer choked us!")
                    peer_choking = True

                elif msg_id == 5:
                    peer_pieces = {
                        p for p in parse_bitfield(payload)
                        if 0 <= p < piece_manager.total_pieces
                    }
                    with piece_manager.lock:
                        for p in peer_pieces:
                            piece_manager.piece_availability[p] += 1
                    print(f"Peer has {len(peer_pieces)} pieces")

                elif msg_id == 4:
                    if len(payload) >= 4:
                        piece_index = int.from_bytes(payload[0:4], "big")

                        if 0 <= piece_index < piece_manager.total_pieces and piece_index not in peer_pieces:
                            peer_pieces.add(piece_index)
                            with piece_manager.lock:
                                piece_manager.piece_availability[piece_index] += 1

                elif msg_id == 7:
                    index = int.from_bytes(payload[0:4], "big")
                    begin = int.from_bytes(payload[4:8], "big")
                    block = payload[8:]

                    pending_requests.pop((index, begin), None)

                    completed_piece = piece_manager.handle_piece_received(index, begin, block)

                    if completed_piece is not None:
                        piece_data = piece_manager.get_piece_data(completed_piece)

                        offset = completed_piece * torrent.piece_length

                        global_offset = completed_piece * torrent.piece_length
                        remaining = len(piece_data)
                        data_offset = 0

                        with file_lock:
                            for f, fh in file_handles:
                                file_start = f["offset"]
                                file_end = file_start + f["length"]

                                if global_offset >= file_end:
                                    continue

                                if global_offset < file_start:
                                    continue

                                write_start = global_offset - file_start
                                write_len = min(remaining, file_end - global_offset)

                                fh.seek(write_start)
                                fh.write(piece_data[data_offset:data_offset+write_len])
                                fh.flush()

                                remaining -= write_len
                                data_offset += write_len
                                global_offset += write_len

                                if remaining <= 0:
                                    break
                        if completed_piece is not None:
                            save_progress(piece_manager)
                        print(f"Wrote piece {completed_piece} to file at offset {offset}")

                        total = piece_manager.total_pieces
                        done = len(piece_manager.completed_pieces)
                        print(f"Progress: {done}/{total} pieces ({(done/total)*100:.2f}%)")

                elif msg_id == 6:
                    if len(payload) < 12:
                        continue

                    index = int.from_bytes(payload[0:4], "big")
                    begin = int.from_bytes(payload[4:8], "big")
                    length = int.from_bytes(payload[8:12], "big")

                    if index < 0 or index >= piece_manager.total_pieces:
                        continue

                    if begin < 0 or length <= 0:
                        continue

                    piece_len = piece_manager.get_piece_length(index)
                    if begin >= piece_len or begin + length > piece_len:
                        continue

                    with piece_manager.lock:
                        has_piece = index in piece_manager.completed_pieces

                    if has_piece:
                        with file_lock:
                            block = read_block_from_files(index, begin, length, torrent, file_handles)

                        if len(block) == length:
                            response = build_piece(index, begin, block)
                            sock.sendall(response)
                            print(f"Uploaded block: piece {index}, begin={begin}, length={length}")


                if not peer_choking and peer_pieces:
                    req = piece_manager.get_next_block_request_for_peer(peer_pieces)

                    if req:
                        index, begin, length = req

                        print(f"Requesting piece {index}, begin={begin}, length={length}")

                        msg = build_request(index, begin, length)
                        sock.sendall(msg)
                        pending_requests[(index, begin)] = time.time()
                    else:
                        time.sleep(0.02)

            except socket.timeout:
                print("Timeout... continuing")
                continue

            except Exception as e:
                print("Error:", e)
                break

    except Exception as e:
        print(f"Fatal error for {peer_label}: {e}")
    finally:
        for index, begin in list(pending_requests.keys()):
            piece_manager.release_block_request(index, begin)

        with piece_manager.lock:
            for piece_index in peer_pieces:
                if 0 <= piece_index < piece_manager.total_pieces and piece_manager.piece_availability[piece_index] > 0:
                    piece_manager.piece_availability[piece_index] -= 1

        if sock:
            try:
                sock.close()
            except Exception:
                pass

file_handles = []
file_lock = threading.Lock()

torrent = Torrent("big-buck-bunny.torrent")

tracker = TrackerClient(torrent)
piece_manager = PieceManager(torrent)

base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloaded-files")

for f in torrent.files_info:
    path = os.path.join(base_dir, f["path"])
    
    os.makedirs(os.path.dirname(path), exist_ok=True)
    
    mode = "r+b" if os.path.exists(path) else "w+b"
    fh = open(path, mode)
    file_handles.append((f, fh))

load_progress(piece_manager, torrent, file_handles, file_lock)

threads = []
peers = tracker.get_peers()
max_active_peers = int(os.getenv("MAX_ACTIVE_PEERS", str(DEFAULT_MAX_ACTIVE_PEERS)))
selected_peers = peers[:max_active_peers]

print("Peers:", selected_peers)

try:
    for ip, port in selected_peers:
        t = threading.Thread(
            target=download_from_peer,
            args=(ip, port, torrent, tracker, piece_manager, file_handles, file_lock)
        )
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    print("Download complete!")
finally:
    for _, fh in file_handles:
        try:
            fh.close()
        except Exception:
            pass