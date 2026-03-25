import urllib.request
import urllib.parse
from bencode import decode
import random
import string
import socket
import struct
import time
import os
import ssl


FALLBACK_HTTP_TRACKERS = [
    "http://tracker.opentrackr.org:1337/announce",
    "http://tracker.openbittorrent.com:80/announce",
    "https://tracker.opentrackr.org:443/announce",
    "https://tracker.btorrent.xyz/announce",
    "https://tracker.tamersunion.org:443/announce",
]

def generate_peer_id():
    rand = ''.join(random.choice(string.digits) for _ in range(12))
    return f"-SH0001-{rand}".encode()

class TrackerClient:

    def __init__(self, torrent):
        self.torrent = torrent
        self.peer_id = generate_peer_id()
        self.port = 6881
        timeout = float(os.getenv("TRACKER_TIMEOUT_SECONDS", "15"))
        retries = int(os.getenv("TRACKER_RETRIES", "2"))
        self.verbose_tracker = os.getenv("TRACKER_VERBOSE", "1") != "0"

        # Guard against stale shell vars like 0.2 that make tracker discovery fail instantly.
        self.tracker_timeout = max(5.0, timeout)
        self.tracker_retries = max(2, retries)
        self.insecure_tracker_ssl = os.getenv("TRACKER_INSECURE_SSL", "1") != "0"


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
        raw_trackers = getattr(self.torrent, "trackers", [self.torrent.announce])
        trackers = [self.torrent.announce] + [t for t in raw_trackers if t != self.torrent.announce]

        # Some networks block UDP trackers; keep a few HTTPS fallbacks for resilience.
        for tracker in FALLBACK_HTTP_TRACKERS:
            if tracker not in trackers:
                trackers.append(tracker)

        errors = []

        for announce_url in trackers:
            scheme = urllib.parse.urlparse(announce_url).scheme.lower()

            if scheme not in ("http", "https", "udp"):
                continue

            for attempt in range(1, self.tracker_retries + 1):
                if self.verbose_tracker:
                    print(f"Tracker announce {attempt}/{self.tracker_retries}: {announce_url}")

                try:
                    if scheme in ("http", "https"):
                        peers = self._get_http_peers(announce_url)
                    else:
                        peers = self._get_udp_peers(announce_url)

                    if peers:
                        return peers

                    errors.append(f"{announce_url} returned no peers")
                    break
                except Exception as e:
                    errors.append(f"{announce_url} attempt {attempt}/{self.tracker_retries}: {e}")
                    if self.verbose_tracker:
                        print(f"Tracker failed: {announce_url} ({e})")
                    if attempt < self.tracker_retries:
                        time.sleep(0.35)
                    continue

        if errors:
            last_lines = "; ".join(errors[-4:])
            raise ValueError(f"Unable to fetch peers from available trackers: {last_lines}")

        raise ValueError(
            "No supported trackers available. "
            "This client currently supports HTTP/HTTPS and UDP trackers."
        )

    def _get_http_peers(self, announce_url):
        url = self.build_tracker_url(announce_url)
        req = urllib.request.Request(url, headers={"User-Agent": "rytorr/0.1"})

        try:
            response = urllib.request.urlopen(req, timeout=self.tracker_timeout).read()
        except urllib.error.URLError as e:
            reason = getattr(e, "reason", None)
            is_ssl_error = isinstance(reason, ssl.SSLError)
            if self.insecure_tracker_ssl and is_ssl_error:
                insecure_ctx = ssl._create_unverified_context()
                response = urllib.request.urlopen(
                    req,
                    timeout=self.tracker_timeout,
                    context=insecure_ctx,
                ).read()
            else:
                raise

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
        last_error = None

        for family, socktype, proto, _, sockaddr in addr_info:
            sock = socket.socket(family, socktype, proto)
            sock.settimeout(self.tracker_timeout)

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
            except Exception as e:
                last_error = e
                continue
            finally:
                sock.close()

        if last_error:
            raise last_error

        raise ValueError("Unable to contact UDP tracker on any resolved address")
    
    def parse_peers(self, peers):
        peers_list = []

        if isinstance(peers, (bytes, bytearray)):
            if len(peers) % 6 != 0:
                raise ValueError("Invalid compact peer list length")

            for i in range(0, len(peers), 6):
                peer = peers[i:i+6]

                ip = ".".join(str(b) for b in peer[:4])
                port = int.from_bytes(peer[4:], "big")

                peers_list.append((ip, port))

            return peers_list

        if isinstance(peers, list):
            for peer in peers:
                if not isinstance(peer, dict):
                    continue

                ip = peer.get("ip")
                port = peer.get("port")

                if isinstance(ip, bytes):
                    ip = ip.decode(errors="ignore")

                if ip is None or port is None:
                    continue

                peers_list.append((str(ip), int(port)))

            return peers_list

        raise TypeError("Unsupported peers format in tracker response")