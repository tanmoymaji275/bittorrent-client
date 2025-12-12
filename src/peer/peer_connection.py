import asyncio
import struct
import time
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
        
        # Download/Upload statistics for rate calculation
        self.downloaded_sample = 0
        self.uploaded_sample = 0
        self.last_reset_time = time.time()
        
        # Choking state from our perspective and peer's perspective
        self.am_choking = True      # We are choking this peer
        self.am_interested = False  # We are interested in this peer
        self.peer_choking = True    # This peer is choking us
        self.peer_interested = False # This peer is interested in us

    async def connect(self):
        # Apply a bounded timeout for TCP connect to avoid long stalls on Windows (e.g., WinError 121)
        CONNECT_TIMEOUT_SECONDS = 5
        try:
            self.reader, self.writer = await asyncio.wait_for(
                asyncio.open_connection(self.ip, self.port),
                timeout=CONNECT_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            raise ConnectionError(
                f"Could not connect to peer {self.ip}:{self.port} -> connection timed out"
            )
        except OSError as e:
            # Map common Windows network errors to a cleaner message
            if getattr(e, "win-error", None) == 121:
                raise ConnectionError(
                    f"Could not connect to peer {self.ip}:{self.port} -> [WinError 121] The semaphore timeout period expired"
                )
            raise ConnectionError(f"Could not connect to peer {self.ip}:{self.port} -> {e}")

        # ---- SEND HANDSHAKE ----
        handshake = build_handshake(self.meta.info_hash, self.peer_id)
        self.writer.write(handshake)
        await self.writer.drain()

        # ---- READ HANDSHAKE ----
        try:
            # use HANDSHAKE_LEN from peer_protocol for clarity, with a bounded read timeout
            HANDSHAKE_TIMEOUT_SECONDS = 5
            resp = await asyncio.wait_for(
                self.reader.readexactly(HANDSHAKE_LEN),
                timeout=HANDSHAKE_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            raise ConnectionError("Timed out waiting for handshake from peer")
        except asyncio.IncompleteReadError:
            raise ConnectionError("Peer closed connection during handshake")

        info_hash, remote_pid = parse_handshake(resp)
        self.remote_peer_id = remote_pid

        if info_hash != self.meta.info_hash:
            raise ValueError("Peer sent a handshake with wrong info_hash")

        # after handshake, peers often send BITFIELD; leave reading to read_message()
        return remote_pid
    
    def reset_stats(self):
        """
        Returns (bytes_downloaded, bytes_uploaded, duration_seconds) since last call.
        Resets counters and timer.
        """
        now = time.time()
        duration = now - self.last_reset_time
        
        d_val = self.downloaded_sample
        u_val = self.uploaded_sample
        
        self.downloaded_sample = 0
        self.uploaded_sample = 0
        self.last_reset_time = now
        
        return d_val, u_val, duration

    def reset_download_stats(self):
        # Alias for backward compatibility if needed, or remove. 
        d, u, t = self.reset_stats()
        return d, t

    async def send(self, msg_id, payload=b"", drain=True):
        if self.closed:
            return

        try:
            msg = build_message(msg_id, payload)
            self.writer.write(msg)
            if drain:
                await self.writer.drain()
            
            # Track upload
            if msg_id == MessageID.PIECE:
                # Payload is index(4) + begin(4) + block
                # Actual data size is len(payload) - 8
                # But strictly speaking, we uploaded the whole payload overhead too.
                # TCP/IP overhead is ignored, but application bytes count.
                self.uploaded_sample += len(payload)
            
            # Update our state tracking
            if msg_id == MessageID.CHOKE:
                self.am_choking = True
            elif msg_id == MessageID.UNCHOKE:
                self.am_choking = False
            elif msg_id == MessageID.INTERESTED:
                self.am_interested = True
            elif msg_id == MessageID.NOT_INTERESTED:
                self.am_interested = False
                
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
            
            # Count bandwidth
            self.downloaded_sample += (length - 1)
            
        except asyncio.IncompleteReadError:
            self.closed = True
            return None, None

        # ------------------------------
        # Handle State Updates
        # ------------------------------
        if msg_id == int(MessageID.CHOKE):
            self.peer_choking = True
        elif msg_id == int(MessageID.UNCHOKE):
            self.peer_choking = False
        elif msg_id == int(MessageID.INTERESTED):
            self.peer_interested = True
        elif msg_id == int(MessageID.NOT_INTERESTED):
            self.peer_interested = False

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