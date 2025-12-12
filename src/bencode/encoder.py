"""
Bencode encoder for BitTorrent metainfo and tracker responses.
"""
from .structure import BencodeDict, BencodeInt, BencodeList, BencodeString


def encode(obj) -> bytes:
    """Encodes a Python object or BencodeType into bencoded bytes."""

    if isinstance(obj, (int, BencodeInt)):
        value = obj if isinstance(obj, int) else obj.value
        return encode_int(value)
    
    if isinstance(obj, (str, BencodeString)):
        if isinstance(obj, str):
            return encode_str(obj)
        # BencodeString wraps bytes
        return encode_bytes(obj.value)
    
    if isinstance(obj, bytes):
        return encode_bytes(obj)

    if isinstance(obj, (list, BencodeList)):
        value = obj if isinstance(obj, list) else obj.value
        return encode_list(value)

    if isinstance(obj, (dict, BencodeDict)):
        value = obj if isinstance(obj, dict) else obj.value
        return encode_dict(value)

    raise TypeError(f"Cannot bencode object of type {type(obj)}")


# ------------------------------------------------------------
#   Encoding primitives
# ------------------------------------------------------------

def encode_int(n: int) -> bytes:
    """Encodes an integer to bencoded bytes (e.g., i123e)."""
    return f"i{n}e".encode()


def encode_bytes(b: bytes) -> bytes:
    """Encodes bytes to bencoded bytes (e.g., 4:spam)."""
    return str(len(b)).encode() + b":" + b


def encode_str(s: str) -> bytes:
    """Encodes a string to bencoded bytes (e.g., 4:spam)."""
    b = s.encode()
    return encode_bytes(b)


def encode_list(lst: list) -> bytes:
    """Encodes a list to bencoded bytes (e.g., l4:spame)."""
    encoded_items = b''.join(encode(x) for x in lst)
    return b"l" + encoded_items + b"e"


def encode_dict(d: dict) -> bytes:
    """Encodes a dictionary to bencoded bytes (e.g., d3:cow3:moo4:spam4:eggse)."""
    result = b"d"

    def key_to_bytes(k):
        return k if isinstance(k, bytes) else k.encode()

    for key in sorted(d.keys(), key=key_to_bytes):
        key_bytes = key_to_bytes(key)
        result += encode_bytes(key_bytes)
        result += encode(d[key])

    return result + b"e"
