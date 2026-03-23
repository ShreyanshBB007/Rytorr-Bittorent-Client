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


def download_from_peer(ip, port, torrent, tracker, piece_manager, file_handles, file_lock):
    try:
        sock = None
        max_attempts = min(len(peers), 20)

        for idx, (ip, port) in enumerate(peers[:max_attempts], start=1):
            print(f"[{idx}/{max_attempts}] Connecting to {ip}:{port}")

            try:
                sock = handshake_with_peer(ip, port, torrent.info_hash, tracker.peer_id)
            except Exception as e:
                print(f"Connection failed for {ip}:{port}: {e}")
                continue

            if sock:
                print(f"Using peer {ip}:{port}")
                break

        if not sock:
            print("Unable to connect/handshake with any peer")
            exit()

        sock.send(build_interested())
        print("Sent INTERESTED")
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
                    peer_pieces = set(parse_bitfield(payload))
                    print(f"Peer has {len(peer_pieces)} pieces")

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
                    req = piece_manager.get_next_block_request()

                    if req:
                        index, begin, length = req

                        if index not in peer_pieces:
                            continue

                        print(f"Requesting piece {index}, begin={begin}, length={length}")

                        msg = build_request(index, begin, length)
                        sock.send(msg)

            except socket.timeout:
                print("Timeout... continuing")
                continue

            except Exception as e:
                print("Error:", e)
                break

    except Exception:
        pass

file_handles = []
file_lock = threading.Lock()

torrent = Torrent("big-buck-bunny.torrent")

tracker = TrackerClient(torrent)
piece_manager = PieceManager(torrent)
output_file = open(torrent.name, "wb")

base_dir = r"C:\Shreyansh\Codes\rytorr-bittorent-client\downloaded-files"

for f in torrent.files_info:
    path = os.path.join(base_dir, f["path"])
    
    os.makedirs(os.path.dirname(path), exist_ok=True)
    
    fh = open(path, "wb")
    file_handles.append((f, fh))

threads = []
peers = tracker.get_peers()

print("Peers:", peers[:5])

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