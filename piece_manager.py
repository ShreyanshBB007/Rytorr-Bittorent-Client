import math

class PieceManager:
    def __init__(self, torrent_data):
        self.piece_length = torrent_data.piece_length
        self.file_length = torrent_data.length
        self.pieces = torrent_data.pieces

        self.total_pieces = math.ceil(self.file_length / self.piece_length)

        if len(self.pieces) % 20 != 0:
            raise ValueError("Invalid pieces length")

        self.piece_hashes = []
        for i in range(0, len(self.pieces), 20):
            self.piece_hashes.append(self.pieces[i:i+20])

        if self.total_pieces != len(self.piece_hashes):
            raise ValueError("Piece count mismatch")

    def get_piece_hash(self, index):
        if index < 0 or index >= self.total_pieces:
            raise IndexError("Invalid piece index")
        return self.piece_hashes[index]