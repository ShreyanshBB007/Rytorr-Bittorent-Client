import socket

def build_handshake(peer_id, info_hash):
    pstr = b'BitTorrent protocol'
    pstrlen  = len(pstr)

    reserved = b'\x00' * 8

    handshake = (
        pstrlen.to_bytes(1, 'big') + pstr + reserved + info_hash + peer_id
    )

    return handshake

def connect_to_peer(ip, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    sock.connect((ip, port))

    return sock

def validate_handshake(response, expected_info_hash):

    if len(response) != 68:
        return False

    pstr = response[1:20]

    if pstr != b"BitTorrent protocol":
        return False

    info_hash = response[28:48]

    if info_hash != expected_info_hash:
        return False

    return True

def handshake_with_peer(ip, port, info_hash, peer_id):

    sock = connect_to_peer(ip, port)

    handshake = build_handshake(peer_id, info_hash)

    sock.send(handshake)

    response = sock.recv(68)

    if validate_handshake(response, info_hash):

        print("Handshake successful")

        return sock

    else:

        sock.close()

        return None
    
def parse_handshake(handshake):

    if len(handshake) != 68:
        raise ValueError("Invalid handshake length")

    pstrlen = handshake[0]
    pstr = handshake[1:20]
    reserved = handshake[20:28]
    info_hash = handshake[28:48]
    peer_id = handshake[48:68]

    return {
        "pstrlen": pstrlen,
        "protocol": pstr,
        "reserved": reserved,
        "info_hash": info_hash,
        "peer_id": peer_id
    }