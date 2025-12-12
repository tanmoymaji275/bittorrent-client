"""
Data structures for representing Bencoded types.
"""
__all__ = [
    "BencodeInt",
    "BencodeString",
    "BencodeList",
    "BencodeDict",
]


class BencodeType:
    """Base class for all Bencode data types."""
    
class BencodeInt(BencodeType):
    """Represents a Bencoded integer."""
    def __init__(self, value: int):
        if not isinstance(value, int):
            raise TypeError("BencodeInt requires an integer.")
        self.value = value

    def __repr__(self):
        return f"BencodeInt({self.value})"


class BencodeString(BencodeType):
    """Represents a Bencoded byte string."""
    def __init__(self, value: bytes):
        if not isinstance(value, (bytes, bytearray)):
            raise TypeError("BencodeString requires bytes.")
        self.value = bytes(value)

    def __repr__(self):
        return f"BencodeString({self.value!r})"


class BencodeList(BencodeType):
    """Represents a Bencoded list."""
    def __init__(self, value: list):
        if not isinstance(value, list):
            raise TypeError("BencodeList requires a list.")
        self.value = value

    def __repr__(self):
        return f"BencodeList({self.value!r})"


class BencodeDict(BencodeType):
    """Represents a Bencoded dictionary."""
    def __init__(self, value: dict):
        if not isinstance(value, dict):
            raise TypeError("BencodeDict requires a dict.")
        # keys must be bytes (bencode requirement)
        for k in value.keys():
            if not isinstance(k, (bytes, bytearray)):
                raise TypeError("BencodeDict keys must be bytes.")
        self.value = value

    def __repr__(self):
        return f"BencodeDict({self.value!r})"
