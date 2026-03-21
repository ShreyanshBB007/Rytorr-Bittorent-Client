def recv_exact(sock, n):
    data = b''

    while len(data) < n:
        chunk = sock.recv(n - len(data))

        if not chunk:
            raise ConnectionError("Peer closed connection")

        data += chunk

    return data


def recv_message(sock):
    length_bytes = recv_exact(sock, 4)
    length = int.from_bytes(length_bytes, "big")

    if length == 0:
        return None, None

    message = recv_exact(sock, length)

    msg_id = message[0]
    payload = message[1:]

    return msg_id, payload