"""
Defines constants for BitTorrent Peer Protocol message IDs and block sizes.
"""
from enum import IntEnum

class MessageID(IntEnum):
    """IDs for standard BitTorrent peer protocol messages."""
    CHOKE = 0
    UNCHOKE = 1
    INTERESTED = 2
    NOT_INTERESTED = 3
    HAVE = 4
    BITFIELD = 5
    REQUEST = 6
    PIECE = 7
    CANCEL = 8

# Standard block size for piece requests
BLOCK_LEN = 16 * 1024   # 16 KB