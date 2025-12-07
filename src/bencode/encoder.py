from .structure import *


def encode(obj) -> bytes:
    """Encode a Python/BencodeType object into bencoded bytes."""

    # --- If you're passing raw Python types ---
    if isinstance(obj, int):
        return encode_int(obj)
    if isinstance(obj, str):
        return encode_str(obj)
    if isinstance(obj, bytes):
        return encode_bytes(obj)
    if isinstance(obj, list):
        return encode_list(obj)
    if isinstance(obj, dict):
        return encode_dict(obj)

    # --- If you're using custom wrapper classes ---
    if isinstance(obj, BencodeInt):
        return encode_int(obj.value)
    if isinstance(obj, BencodeString):
        return encode_bytes(obj.value)
    if isinstance(obj, BencodeList):
        return encode_list(obj.value)
    if isinstance(obj, BencodeDict):
        return encode_dict(obj.value)

    raise TypeError(f"Cannot bencode object of type {type(obj)}")


# ------------------------------------------------------------
#   Encoding primitives
# ------------------------------------------------------------

def encode_int(n: int) -> bytes:
    return f"i{n}e".encode()


def encode_bytes(b: bytes) -> bytes:
    return str(len(b)).encode() + b":" + b


def encode_str(s: str) -> bytes:
    b = s.encode()
    return encode_bytes(b)


def encode_list(lst: list) -> bytes:
    encoded_items = b''.join(encode(x) for x in lst)
    return b"l" + encoded_items + b"e"


def encode_dict(d: dict) -> bytes:
    result = b"d"

    # Keys must be sorted lexicographically (as raw bytes)
    for key in sorted(d.keys()):
        key_bytes = key.encode()  # keys are always strings
        result += encode_bytes(key_bytes)
        result += encode(d[key])

    return result + b"e"

