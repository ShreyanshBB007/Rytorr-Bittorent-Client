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

    def get_next_block_request(self):
        for piece_index in self.in_progress_pieces:
            piece = self.pieces[piece_index]
            block = piece.get_next_block()

            if block is not None:
                begin, length = block
                return (piece_index, begin, length)

        if self.missing_pieces:
            piece_index = self.missing_pieces.pop()
            self.in_progress_pieces.add(piece_index)

            piece = self.pieces[piece_index]
            block = piece.get_next_block()

            if block is not None:
                begin, length = block
                return (piece_index, begin, length)

        return None

    def handle_piece_received(self, piece_index, begin, data):
        if piece_index < 0 or piece_index >= self.total_pieces:
            return None

        if piece_index in self.completed_pieces:
            return None

        piece = self.pieces[piece_index]

        piece.add_block(begin, data)

        if piece.is_complete():
            expected_hash = self.get_piece_hash(piece_index)

            if piece.verify(expected_hash):
                self.in_progress_pieces.discard(piece_index)
                self.completed_pieces.add(piece_index)

                print(f"Piece {piece_index} completed and verified")

                return piece_index   # 🔥 THIS LINE IS MISSING IN YOUR CODE

            else:
                print(f"Piece {piece_index} failed verification, retrying")

                piece.reset()
                self.in_progress_pieces.discard(piece_index)
                self.missing_pieces.add(piece_index)

        return None      
    
    def get_piece_data(self, index):
        return self.pieces[index].assemble()
    
    def is_complete(self):
        return len(self.completed_pieces) == self.total_pieces


class Piece:
    def __init__(self, index, piece_length, block_size=16384):

        self.index = index
        self.piece_length = piece_length
        self.block_size = block_size

        self.num_blocks = math.ceil(piece_length / block_size)

        self.blocks_received = [False] * self.num_blocks
        self.blocks_requested = [False] * self.num_blocks
        self.blocks_data = [None] * self.num_blocks

    def add_block(self, begin, data):
        block_index = begin // self.block_size

        if block_index >= self.num_blocks:
            return

        if not self.blocks_received[block_index]:
            self.blocks_data[block_index] = data
            self.blocks_received[block_index] = True

    def get_next_block(self):
        for i in range(self.num_blocks):
            if not self.blocks_received[i] and not self.blocks_requested[i]:
                self.blocks_requested[i] = True
                begin = i * self.block_size
                length = min(self.block_size, self.piece_length - begin)
                return (begin, length)
        return None

    def is_complete(self):
        return all(self.blocks_received)

    def assemble(self):
        return b''.join(self.blocks_data)

    def verify(self, expected_hash):
        piece_data = self.assemble()
        return hashlib.sha1(piece_data).digest() == expected_hash

    def reset(self):
        self.blocks_received = [False] * self.num_blocks
        self.blocks_requested = [False] * self.num_blocks
        self.blocks_data = [None] * self.num_blocks