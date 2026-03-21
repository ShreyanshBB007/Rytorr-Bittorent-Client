import urllib.request
import urllib.parse
from bencode import decode
import random
import string
import socket
import struct

def generate_peer_id():
    rand = ''.join(random.choice(string.digits) for _ in range(12))
    return f"-SH0001-{rand}".encode()

class TrackerClient:

    def __init__(self, torrent):
        self.torrent = torrent
        self.peer_id = generate_peer_id()
        self.port = 6881


    def build_tracker_url(self, announce_url=None):

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

        base_url = announce_url or self.torrent.announce
        return base_url + "?" + query


    def get_peers(self):
        trackers = getattr(self.torrent, "trackers", [self.torrent.announce])
        last_error = None

        for announce_url in trackers:
            scheme = urllib.parse.urlparse(announce_url).scheme.lower()

            if scheme not in ("http", "https", "udp"):
                continue

            try:
                if scheme in ("http", "https"):
                    return self._get_http_peers(announce_url)
                return self._get_udp_peers(announce_url)
            except Exception as e:
                last_error = e
                continue

        if last_error:
            raise ValueError(f"Unable to fetch peers from available trackers: {last_error}")

        raise ValueError(
            "No supported trackers available. "
            "This client currently supports HTTP/HTTPS and UDP trackers."
        )

    def _get_http_peers(self, announce_url):
        url = self.build_tracker_url(announce_url)
        response = urllib.request.urlopen(url, timeout=10).read()
        decoded, _ = decode(response)
        peers = decoded["peers"]
        return self.parse_peers(peers)

    def _get_udp_peers(self, announce_url):
        parsed = urllib.parse.urlparse(announce_url)
        host = parsed.hostname
        port = parsed.port or 80

        if not host:
            raise ValueError("Invalid UDP tracker URL: missing hostname")

        addr_info = socket.getaddrinfo(host, port, type=socket.SOCK_DGRAM)
        family, socktype, proto, _, sockaddr = addr_info[0]

        sock = socket.socket(family, socktype, proto)
        sock.settimeout(10)

        try:
            # Step 1: connect request
            transaction_id = random.getrandbits(32)
            connect_req = struct.pack("!QII", 0x41727101980, 0, transaction_id)
            sock.sendto(connect_req, sockaddr)

            connect_resp, _ = sock.recvfrom(2048)
            if len(connect_resp) < 16:
                raise ValueError("Invalid UDP tracker connect response")

            action, returned_txn, connection_id = struct.unpack("!IIQ", connect_resp[:16])
            if action != 0 or returned_txn != transaction_id:
                raise ValueError("UDP tracker connect response validation failed")

            # Step 2: announce request
            announce_txn = random.getrandbits(32)
            key = random.getrandbits(32)
            announce_req = struct.pack(
                "!QII20s20sQQQIIIiH",
                connection_id,
                1,
                announce_txn,
                self.torrent.info_hash,
                self.peer_id,
                0,
                self.torrent.length,
                0,
                0,
                0,
                key,
                -1,
                self.port,
            )
            sock.sendto(announce_req, sockaddr)

            announce_resp, _ = sock.recvfrom(8192)
            if len(announce_resp) < 20:
                raise ValueError("Invalid UDP tracker announce response")

            action, returned_txn, _interval, _leechers, _seeders = struct.unpack(
                "!IIIII", announce_resp[:20]
            )
            if action != 1 or returned_txn != announce_txn:
                raise ValueError("UDP tracker announce response validation failed")

            peers = announce_resp[20:]
            return self.parse_peers(peers)
        finally:
            sock.close()
    
    def parse_peers(self, peers):
        peers_list = []

        for i in range(0, len(peers), 6):
            peer = peers[i:i+6]

            ip = ".".join(str(b) for b in peer[:4])
            port = int.from_bytes(peer[4:], "big")

            peers_list.append((ip,port))

        return peers_list