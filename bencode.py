def decode_int(data, index):
    end = data.index(b'e', index)
    num = int(data[index+1:end])
    return num, end + 1


def decode_string(data, index):
    colon = data.index(b":", index)
    length = int(data[index:colon])
    start = colon + 1
    end = start + length
    return data[start:end], end


def decode_list(data, index):
    items = []
    index += 1

    while data[index:index+1] != b'e':

        if data[index:index+1] == b'i':
            val, index = decode_int(data, index)

        elif data[index:index+1] == b'l':
            val, index = decode_list(data, index)

        elif data[index:index+1] == b'd':
            val, index = decode_dict(data, index)

        else:
            val, index = decode_string(data, index)

        items.append(val)

    return items, index + 1


def decode_dict(data, index):
    items = {}
    index += 1

    while data[index:index+1] != b'e':

        keystring, index = decode_string(data, index)

        if data[index:index+1] == b'i':
            val, index = decode_int(data, index)

        elif data[index:index+1] == b'l':
            val, index = decode_list(data, index)

        elif data[index:index+1] == b'd':
            val, index = decode_dict(data, index)

        else:
            val, index = decode_string(data, index)

        items[keystring.decode()] = val

    return items, index + 1


def decode(data, index=0):

    char = data[index:index+1]

    if char == b'i':
        return decode_int(data, index)

    elif char == b'l':
        return decode_list(data, index)

    elif char == b'd':
        return decode_dict(data, index)

    else:
        return decode_string(data, index)