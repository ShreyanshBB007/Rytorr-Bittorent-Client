import hashlib
from bencode import decode

class Torrent:
    def __init__(self, path):
        with open(path, "rb") as f:
            data = f.read()

        decoded, _ = decode(data)

        self.announce = decoded["announce"].decode()
        self.info = decoded["info"]
        self.name = self.info["name"].decode()
        self.piece_length = self.info["piece length"]
        self.pieces = self.info["pieces"]

        if "length" in self.info:
            self.length = self.info["length"]

        self.info_hash = hashlib.sha1(self._get_info_bytes(data)).digest()

    def _get_info_bytes(self, data):
        start = data.index(b"4:info") + len("4:info")

        info_bytes = data[start:]

        return info_bytes