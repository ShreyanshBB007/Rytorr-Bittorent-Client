from torrent_parser import Torrent
from tracker_client import TrackerClient
from peer_connection import handshake_with_peer

torrent = Torrent("sintel.torrent")

tracker = TrackerClient(torrent)

peers = tracker.get_peers()

for ip, port in peers[:5]:

    sock = handshake_with_peer(
        ip,
        port,
        torrent.info_hash,
        tracker.peer_id
    )

    if sock:
        print("Connected to", ip)
