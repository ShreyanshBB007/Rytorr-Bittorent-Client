from torrent_parser import Torrent
from tracker_client import TrackerClient
from peer_connection import handshake_with_peer
from peer_messages import build_interested
from downloader import recv_message

# Step 1: Load torrent
torrent = Torrent("big-buck-bunny.torrent")  # <-- your file

# Step 2: Get peers
tracker = TrackerClient(torrent)
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
while True:
    try:
        msg_id, payload = recv_message(sock)

        if msg_id is None:
            print("Keep-alive")
            continue

        print("Received message ID:", msg_id)

    except Exception as e:
        print("Error:", e)
        break