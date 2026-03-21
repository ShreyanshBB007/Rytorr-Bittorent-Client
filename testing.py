from torrent_parser import Torrent
from tracker_client import TrackerClient
from peer_connection import handshake_with_peer
from peer_messages import build_interested
from peer_messages import build_request
from downloader import recv_message
from piece_manager import PieceManager

# Step 1: Load torrent
torrent = Torrent("big-buck-bunny.torrent")  # <-- your file

# Step 2: Get peers
tracker = TrackerClient(torrent)
piece_manager = PieceManager(torrent)
peers = tracker.get_peers()

print("Peers:", peers[:5])

# Step 3: Try multiple peers until one handshake succeeds
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

# Step 5: Send INTERESTED
sock.send(build_interested())
print("Sent INTERESTED")
sock.settimeout(15)
# Step 6: Receive messages
peer_choking = True
while True:
    try:
        msg_id, payload = recv_message(sock)
        if msg_id == 1:  # UNCHOKE
            print("Peer unchoked us!")
            peer_choking = False

        elif msg_id == 0:  # CHOKE
            print("Peer choked us!")
            peer_choking = True

        elif msg_id == 7:  # PIECE
            index = int.from_bytes(payload[0:4], "big")
            begin = int.from_bytes(payload[4:8], "big")
            block = payload[8:]

            print(f"Received block: piece {index}, begin={begin}, size={len(block)}")

            piece_manager.handle_piece_received(index, begin, block)

        if msg_id is None:
            print("Keep-alive")
            continue

        print("Received message ID:", msg_id)

        if not peer_choking:
            req = piece_manager.get_next_block_request()

            if req:
                index, begin, length = req

                print(f"Requesting piece {index}, begin={begin}, length={length}")

                msg = build_request(index, begin, length)
                sock.send(msg)

    except Exception as e:
        print("Error:", e)
        break