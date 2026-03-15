def parse_bitfield(bitfield):

    pieces = []

    for byte_index, byte in enumerate(bitfield):

        for bit in range(8):

            if byte & (1 << (7 - bit)):
                piece_index = byte_index * 8 + bit
                pieces.append(piece_index)

    return pieces

def build_interested():

    length = (1).to_bytes(4, "big")

    msg_id = b'\x02'

    return length + msg_id

def build_request(piece_index, begin, block_length):

    length_prefix = (13).to_bytes(4, "big")

    msg_id = b'\x06'

    index_bytes = piece_index.to_bytes(4, "big")

    begin_bytes = begin.to_bytes(4, "big")

    length_bytes = block_length.to_bytes(4, "big")

    return length_prefix + msg_id + index_bytes + begin_bytes + length_bytes