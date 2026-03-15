import hashlib
import urllib.parse
from bencode import decode

class Torrent:
    def __init__(self, path):
        with open(path, "rb") as f:
            data = f.read()

        decoded, _ = decode(data)

        self.announce = decoded["announce"].decode()
        self.trackers = self._extract_trackers(decoded)
        self.announce = self._select_http_tracker(self.trackers, self.announce)
        self.info = decoded["info"]
        self.name = self.info["name"].decode()
        self.piece_length = self.info["piece length"]
        self.pieces = self.info["pieces"]

        if "length" in self.info:
            self.length = self.info["length"]
        else:
            self.length = sum(f["length"] for f in self.info["files"])

        self.info_hash = hashlib.sha1(self._get_info_bytes(data)).digest()

    def _get_info_bytes(self, data):
        start = data.index(b"4:info") + len("4:info")

        info_bytes = data[start:]

        return info_bytes

    def _extract_trackers(self, decoded):
        trackers = [decoded["announce"].decode()]

        announce_list = decoded.get("announce-list")
        if not announce_list:
            return trackers

        for tier in announce_list:
            for tracker in tier:
                try:
                    trackers.append(tracker.decode())
                except Exception:
                    continue

        # Preserve order while removing duplicates.
        return list(dict.fromkeys(trackers))

    def _select_http_tracker(self, trackers, fallback):
        for tracker in trackers:
            scheme = urllib.parse.urlparse(tracker).scheme.lower()
            if scheme in ("http", "https"):
                return tracker

        return fallback