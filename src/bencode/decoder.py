from .structure import *


class BencodeDecodeError(Exception):
    pass


class BencodeDecoder:
    def __init__(self, data: bytes):
        self.data = data
        self.i = 0  # cursor index

    def decode(self):
        """Main decode entry."""
        result = self._parse_value()
        return result

    # --------------------------
    # Low-level utilities
    # --------------------------

    def _peek(self):
        if self.i >= len(self.data):
            raise BencodeDecodeError("Unexpected end of input")
        return self.data[self.i:self.i+1]

    def _consume(self, n=1):
        """Move cursor forward by n bytes."""
        chunk = self.data[self.i:self.i+n]
        self.i += n
        return chunk

    # --------------------------
    # Parsing functions
    # --------------------------

    def _parse_value(self):
        ch = self._peek()

        if ch == b'i':
            return self._parse_int()

        elif ch.isdigit():
            return self._parse_string()

        elif ch == b'l':
            return self._parse_list()

        elif ch == b'd':
            return self._parse_dict()

        else:
            raise BencodeDecodeError(f"Invalid token at index {self.i}: {ch}")

    def _parse_int(self):
        self._consume(1)  # skip 'i'

        end_pos = self.data.index(b'e', self.i)
        number_bytes = self.data[self.i:end_pos]

        try:
            num = int(number_bytes)
        except ValueError:
            raise BencodeDecodeError("Invalid integer format")

        self.i = end_pos + 1  # skip 'e'
        return BencodeInt(num)

    def _parse_string(self):
        # read length until ':'
        colon = self.data.index(b':', self.i)
        length_bytes = self.data[self.i:colon]

        try:
            length = int(length_bytes)
        except ValueError:
            raise BencodeDecodeError("Invalid string length")

        self.i = colon + 1
        string_bytes = self._consume(length)

        return BencodeString(string_bytes)

    def _parse_list(self):
        self._consume(1)  # skip 'l'
        items = []

        while self._peek() != b'e':
            items.append(self._parse_value())

        self._consume(1)  # skip 'e'
        return BencodeList(items)

    def _parse_dict(self):
        self._consume(1)  # skip 'd'
        obj = {}

        while self._peek() != b'e':
            # keys MUST be strings
            key = self._parse_string().value
            value = self._parse_value()
            obj[key] = value

        self._consume(1)  # skip 'e'
        return BencodeDict(obj)


# ------------------------------------------------
# For convenience of usage outside this file
# ------------------------------------------------

def decode(data: bytes):
    """Shortcut function: decode and return root bencode object."""
    return BencodeDecoder(data).decode()
