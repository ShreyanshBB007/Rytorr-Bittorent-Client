import math
import hashlib


class PieceManager:
    def __init__(self, torrent_data):

        self.piece_length = torrent_data.piece_length
        self.file_length = torrent_data.length
        self.raw_pieces = torrent_data.pieces

        self.total_pieces = math.ceil(self.file_length / self.piece_length)

        self.completed_pieces = set()
        self.in_progress_pieces = set()
        self.missing_pieces = set(range(self.total_pieces))

        if len(self.raw_pieces) % 20 != 0:
            raise ValueError("Invalid pieces length")

        self.piece_hashes = []
        for i in range(0, len(self.raw_pieces), 20):
            self.piece_hashes.append(self.raw_pieces[i:i+20])

        if self.total_pieces != len(self.piece_hashes):
            raise ValueError("Piece count mismatch")

        self.pieces = []

        for i in range(self.total_pieces):
            if i == self.total_pieces - 1:
                piece_len = self.file_length - ((self.total_pieces - 1) * self.piece_length)
            else:
                piece_len = self.piece_length

            self.pieces.append(Piece(i, piece_len))

    def get_piece_hash(self, index):
        if index < 0 or index >= self.total_pieces:
            raise IndexError("Invalid piece index")
        return self.piece_hashes[index]


class Piece:
    def __init__(self, index, piece_length, block_size=16384):
        
        self.index = index
        self.piece_length = piece_length
        self.block_size = block_size

        self.num_blocks = math.ceil(piece_length / block_size)

        self.blocks_received = [False] * self.num_blocks
        self.blocks_data = [None] * self.num_blocks

    def add_block(self, begin, data):
        block_index = begin // self.block_size

        if block_index >= self.num_blocks:
            return

        if not self.blocks_received[block_index]:
            self.blocks_data[block_index] = data
            self.blocks_received[block_index] = True

    def is_complete(self):
        return all(self.blocks_received)

    def assemble(self):
        return b''.join(self.blocks_data)

    def verify(self, expected_hash):
        piece_data = self.assemble()
        return hashlib.sha1(piece_data).digest() == expected_hash