from enum import IntEnum

class MessageID(IntEnum):
    CHOKE = 0
    UNCHOKE = 1
    INTERESTED = 2
    NOT_INTERESTED = 3
    HAVE = 4
    BITFIELD = 5
    REQUEST = 6
    PIECE = 7
    CANCEL = 8

# Block size
BLOCK_LEN = 16 * 1024   # 16 KB