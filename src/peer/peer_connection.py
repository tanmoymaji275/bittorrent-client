import asyncio
import struct
from .peer_protocol import build_handshake, parse_handshake, build_message, HANDSHAKE_LEN
from .message_types import MessageID

class PeerConnection:
    def __init__(self, ip, port, torrent_meta, peer_id):
        self.reader = None
        self.writer = None
        self.ip = ip
        self.port = port
        self.meta = torrent_meta
        self.peer_id = peer_id
        self.remote_peer_id = None
        self.closed = False

        # Raw bitfield bytes (or None if not received)
        self.bitfield = None
        # Set of piece indices learned via HAVE messages
        self.have = set()

    async def connect(self):
        try:
            self.reader, self.writer = await asyncio.open_connection(self.ip, self.port)
        except Exception as e:
            raise ConnectionError(f"Could not connect to peer {self.ip}:{self.port} → {e}")

        # ---- SEND HANDSHAKE ----
        handshake = build_handshake(self.meta.info_hash, self.peer_id)
        self.writer.write(handshake)
        await self.writer.drain()

        # ---- READ HANDSHAKE ----
        try:
            # use HANDSHAKE_LEN from peer_protocol for clarity
            resp = await self.reader.readexactly(HANDSHAKE_LEN)
        except asyncio.IncompleteReadError:
            raise ConnectionError("Peer closed connection during handshake")

        info_hash, remote_pid = parse_handshake(resp)
        self.remote_peer_id = remote_pid

        if info_hash != self.meta.info_hash:
            raise ValueError("Peer sent a handshake with wrong info_hash")

        # after handshake, peers often send BITFIELD; leave reading to read_message()
        return remote_pid

    async def send(self, msg_id, payload=b""):
        if self.closed:
            return

        try:
            msg = build_message(msg_id, payload)
            self.writer.write(msg)
            await self.writer.drain()
        except Exception:
            self.closed = True
            raise

    async def read_message(self):
        """Reads and parses the next framed peer message.

        Returns:
            tuple: (msg_id, payload) or (None, None) on connection close/error.
            Note: 'keepalive' is returned as msg_id for keep-alive messages.
        """
        try:
            header = await self.reader.readexactly(4)
        except asyncio.IncompleteReadError:
            self.closed = True
            return None, None

        length = struct.unpack(">I", header)[0]

        if length == 0:
            # keep-alive message
            return "keepalive", None

        try:
            msg_id = (await self.reader.readexactly(1))[0]
            payload = await self.reader.readexactly(length - 1)
        except asyncio.IncompleteReadError:
            self.closed = True
            return None, None

        # ------------------------------
        # Handle BITFIELD and HAVE
        # ------------------------------
        # MessageID constants come from message_types.py
        if msg_id == int(MessageID.BITFIELD):
            # BITFIELD payload is a raw bitmap of pieces (big-endian within each byte)
            # store bytes directly for later queries
            self.bitfield = payload  # bytes
            return msg_id, payload

        if msg_id == int(MessageID.HAVE):
            # HAVE payload is 4-byte piece index (big-endian)
            if len(payload) >= 4:
                piece_index = int.from_bytes(payload[:4], "big")
                self.have.add(piece_index)
            else:
                # malformed HAVE — ignore but return it
                pass
            return msg_id, payload

        # For all other messages, just return as before
        return msg_id, payload

    def has_piece(self, idx: int) -> bool:
        """Return True if the peer appears to have piece idx.

        Checks:
          1) explicit HAVE messages (self.have)
          2) bitfield bytes (self.bitfield) if present

        If neither is present, returns False (unknown).
        """
        # Check explicit HAVE set first
        if idx in self.have:
            return True

        # If we have a bitfield, decode it:
        if self.bitfield:
            byte_index = idx // 8
            if byte_index < len(self.bitfield):
                # Bits in bitfield are ordered MSB -> LSB per spec
                bit_in_byte = 7 - (idx % 8)
                return ((self.bitfield[byte_index] >> bit_in_byte) & 1) == 1

        return False

    def available_pieces(self):
        # Return an iterable of piece indices this peer claims to have.
        # Prefer bitfield if present (gives full view)
        if self.bitfield:
            bits = []
            total_pieces = self.meta.num_pieces
            for idx in range(total_pieces):
                if self.has_piece(idx):
                    bits.append(idx)
            return bits

        # Fallback to explicit HAVE messages
        return sorted(self.have)

    def close(self):
        if self.closed or self.writer is None:
            return

        self.writer.close()

        # Try waiting for close only if inside an event loop
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.writer.wait_closed())
        except RuntimeError:
            # No running loop (close called outside async context)
            pass

        self.closed = True