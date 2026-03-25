import json
import hashlib


def _read_piece_from_files(piece_index, piece_length, torrent, file_handles, file_lock):
    global_offset = piece_index * torrent.piece_length
    remaining = piece_length
    chunks = []

    with file_lock:
        for f, fh in file_handles:
            file_start = f["offset"]
            file_end = file_start + f["length"]

            if global_offset >= file_end:
                continue

            if global_offset < file_start:
                continue

            read_start = global_offset - file_start
            read_len = min(remaining, file_end - global_offset)

            fh.seek(read_start)
            chunks.append(fh.read(read_len))

            remaining -= read_len
            global_offset += read_len

            if remaining <= 0:
                break

    return b"".join(chunks)

def save_progress(piece_manager, filename="progress.resume"):
    data = {
        "completed_pieces": list(piece_manager.completed_pieces)
    }

    with open(filename, "w") as f:
        json.dump(data, f)

def load_progress(piece_manager, torrent, file_handles, file_lock, filename="progress.resume"):
    try:
        with open(filename, "r") as f:
            data = json.load(f)

        completed = data.get("completed_pieces")
        if not isinstance(completed, list):
            raise ValueError("Invalid resume format: completed_pieces must be a list")

        verified_count = 0

        for p in completed:
            if not isinstance(p, int):
                continue

            if p < 0 or p >= piece_manager.total_pieces:
                continue

            piece_length = piece_manager.get_piece_length(p)
            piece_data = _read_piece_from_files(p, piece_length, torrent, file_handles, file_lock)

            if len(piece_data) != piece_length:
                continue

            expected_hash = piece_manager.get_piece_hash(p)
            if hashlib.sha1(piece_data).digest() != expected_hash:
                continue

            piece_manager.completed_pieces.add(p)
            piece_manager.missing_pieces.discard(p)
            verified_count += 1

        print(f"Resumed {verified_count} verified pieces")

    except FileNotFoundError:
        print("No resume file found, starting fresh")
    except (json.JSONDecodeError, ValueError, TypeError, KeyError):
        print("Invalid resume file, starting fresh")