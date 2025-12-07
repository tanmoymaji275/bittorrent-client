import struct
from typing import Tuple, Optional
from .message_types import MessageID

PROTOCOL_STR = b"BitTorrent protocol"
HANDSHAKE_LEN = 1 + len(PROTOCOL_STR) + 8 + 20 + 20  # pstrlen + pstr + reserved + info_hash + peer_id

def build_handshake(info_hash: bytes, peer_id: bytes) -> bytes:
    """
    Build a handshake message.
    info_hash: 20 bytes
    peer_id:   20 bytes
    """
    if len(info_hash) != 20 or len(peer_id) != 20:
        raise ValueError("info_hash and peer_id must be 20 bytes each")

    return (
        bytes([len(PROTOCOL_STR)]) +
        PROTOCOL_STR +
        b"\x00" * 8 +   # 8 reserved bytes, leave zeroed for now
        info_hash +
        peer_id
    )

def parse_handshake(data: bytes) -> Tuple[bytes, bytes]:
    """
    Parse handshake bytes and return (info_hash, peer_id).
    Raises ValueError if invalid handshake.
    """
    if len(data) < HANDSHAKE_LEN:
        raise ValueError("Handshake too short")

    pstrlen = data[0]
    pstr = data[1:1+pstrlen]
    if pstr != PROTOCOL_STR:
        raise ValueError(f"Invalid protocol string: {pstr!r}")

    offset = 1 + pstrlen
    offset += 8     # 8 reserved bytes
    info_hash = data[offset: offset + 20]
    offset += 20
    peer_id = data[offset: offset + 20]

    if len(info_hash) != 20 or len(peer_id) != 20:
        raise ValueError("Handshake fields malformed")

    return info_hash, peer_id

# ---- Message framing helpers ----
def build_message(msg_id: MessageID, payload: bytes = b"") -> bytes:
    """
    Frame a message: 4-byte big-endian length + 1-byte id + payload
    length = 1 + len(payload)
    """
    length = 1 + len(payload)
    return struct.pack(">I", length) + bytes([int(msg_id)]) + payload   # ">" → big-endian
                                                                                # "I" → unsigned 4-byte integer

def parse_message(stream_bytes: bytes) -> Optional[tuple]:
    if len(stream_bytes) < 4:
        return None

    length = struct.unpack(">I", stream_bytes[:4])[0]
    if length == 0:
        # keep-alive (4 bytes header only)
        return "keep-alive", b"", 4

    total_needed = 4 + length
    if len(stream_bytes) < total_needed:
        return None

    msg_id = stream_bytes[4]
    payload = stream_bytes[5:total_needed]
    return msg_id, payload, total_needed
