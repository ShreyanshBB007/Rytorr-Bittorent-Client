import urllib.request
import urllib.parse
from bencode import decode
import random
import string

def generate_peer_id():
    rand = ''.join(random.choice(string.digits) for _ in range(12))
    return f"-SH0001-{rand}".encode()

class TrackerClient:

    def __init__(self, torrent):
        self.torrent = torrent
        self.peer_id = generate_peer_id()
        self.port = 6881


    def build_tracker_url(self):

        params = {
            "info_hash": self.torrent.info_hash,
            "peer_id": self.peer_id,
            "port": self.port,
            "uploaded": 0,
            "downloaded": 0,
            "left": self.torrent.length,
            "compact": 1
        }

        query = urllib.parse.urlencode(params)

        return self.torrent.announce + "?" + query


    def get_peers(self):

        url = self.build_tracker_url()
        scheme = urllib.parse.urlparse(url).scheme.lower()

        if scheme not in ("http", "https"):
            raise ValueError(
                f"Unsupported tracker scheme '{scheme}'. "
                "This client currently supports only HTTP/HTTPS trackers."
            )

        response = urllib.request.urlopen(url, timeout=10).read()

        decoded, _ = decode(response)

        peers = decoded["peers"]

        return self.parse_peers(peers)
    
    def parse_peers(self, peers):
        peers_list = []

        for i in range(0, len(peers), 6):
            peer = peers[i:i+6]

            ip = ".".join(str(b) for b in peer[:4])
            port = int.from_bytes(peer[4:], "big")

            peers_list.append((ip,port))

        return peers_list