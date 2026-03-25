from torrent_parser import Torrent
from tracker_client import TrackerClient
from peer_connection import handshake_with_peer
from peer_messages import build_interested
from peer_messages import build_request
from downloader import recv_message
from piece_manager import PieceManager
from peer_messages import parse_bitfield
import socket
import os
import threading
import time


def download_from_peer(ip, port, torrent, tracker, piece_manager, file_handles, file_lock):
    sock = None
    peer_label = f"{ip}:{port}"

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

        sock.send(build_interested())
        print(f"Sent INTERESTED to {peer_label}")
        sock.settimeout(15)

        peer_choking = True
        peer_pieces = set()

        while not piece_manager.is_complete():
            try:
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

                        print(f"Wrote piece {completed_piece} to file at offset {offset}")

                        total = piece_manager.total_pieces
                        done = len(piece_manager.completed_pieces)
                        print(f"Progress: {done}/{total} pieces ({(done/total)*100:.2f}%)")


                if not peer_choking and peer_pieces:
                    req = piece_manager.get_next_block_request_for_peer(peer_pieces)

                    if req:
                        index, begin, length = req

                        print(f"Requesting piece {index}, begin={begin}, length={length}")

                        msg = build_request(index, begin, length)
                        sock.send(msg)
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

base_dir = r"C:\Shreyansh\Codes\rytorr-bittorent-client\downloaded-files"

for f in torrent.files_info:
    path = os.path.join(base_dir, f["path"])
    
    os.makedirs(os.path.dirname(path), exist_ok=True)
    
    fh = open(path, "wb")
    file_handles.append((f, fh))

threads = []
peers = tracker.get_peers()

print("Peers:", peers[:5])

try:
    for ip, port in peers[:5]:
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