import asyncio
import struct
import time

from .message_types import MessageID
from .peer_protocol import build_handshake, parse_handshake, build_message, HANDSHAKE_LEN


class PeerConnection:
    """
    Manages a single TCP connection to a peer, including handshake,
    message sending/receiving, and state tracking.
    """
    def __init__(self, ip, port, torrent_meta, peer_id):
        self.reader = None
        self.writer = None
        self.ip = ip
        self.port = port
        self.meta = torrent_meta
        self.peer_id = peer_id
        self.remote_peer_id = None
        self.closed = False

        self.bitfield = None
        self.have = set()
        
        self.downloaded_sample = 0
        self.uploaded_sample = 0
        self.last_reset_time = time.time()
        
        self.am_choking = True
        self.am_interested = False
        self.peer_choking = True
        self.peer_interested = False

    async def connect(self):
        connect_timeout_seconds = 5
        try:
            self.reader, self.writer = await asyncio.wait_for(
                asyncio.open_connection(self.ip, self.port),
                timeout=connect_timeout_seconds,
            )
        except asyncio.TimeoutError:
            raise ConnectionError(
                f"Could not connect to peer {self.ip}:{self.port} -> connection timed out"
            )
        except OSError as e:
            if getattr(e, "win-error", None) == 121:
                raise ConnectionError(
                    f"Could not connect to peer {self.ip}:{self.port} -> [WinError 121] The semaphore timeout period expired"
                ) from e
            raise ConnectionError(f"Could not connect to peer {self.ip}:{self.port} -> {e}") from e

        handshake = build_handshake(self.meta.info_hash, self.peer_id)
        self.writer.write(handshake)
        await self.writer.drain()

        try:
            handshake_timeout_seconds = 5
            resp = await asyncio.wait_for(
                self.reader.readexactly(HANDSHAKE_LEN),
                timeout=handshake_timeout_seconds,
            )
        except asyncio.TimeoutError:
            raise ConnectionError("Timed out waiting for handshake from peer")
        except asyncio.IncompleteReadError:
            raise ConnectionError("Peer closed connection during handshake")

        info_hash, remote_pid = parse_handshake(resp)
        self.remote_peer_id = remote_pid

        if info_hash != self.meta.info_hash:
            raise ValueError("Peer sent a handshake with wrong info_hash")

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
        # This method is not used. Keeping for now but could be removed.
        d, _, t = self.reset_stats() # _ is for unused uploaded_sample
        return d, t

    async def send(self, msg_id, payload=b"", drain=True):
        if self.closed:
            return

        try:
            msg = build_message(msg_id, payload)
            self.writer.write(msg)
            if drain:
                await self.writer.drain()
            
            if msg_id == MessageID.PIECE:
                # payload contains (index + begin + block_data). We count the block_data size.
                self.uploaded_sample += len(payload) - 8 
            
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
            'keepalive' is returned as msg_id for keep-alive messages.
        """
        try:
            header = await self.reader.readexactly(4)
        except asyncio.IncompleteReadError:
            self.closed = True
            return None, None

        length = struct.unpack(">I", header)[0]

        if length == 0:
            return "keepalive", None

        try:
            msg_id = (await self.reader.readexactly(1))[0]
            payload = await self.reader.readexactly(length - 1)
            
            self.downloaded_sample += (length - 1)
            
        except asyncio.IncompleteReadError:
            self.closed = True
            return None, None

        if msg_id == int(MessageID.CHOKE):
            self.peer_choking = True
        elif msg_id == int(MessageID.UNCHOKE):
            self.peer_choking = False
        elif msg_id == int(MessageID.INTERESTED):
            self.peer_interested = True
        elif msg_id == int(MessageID.NOT_INTERESTED):
            self.peer_interested = False

        if msg_id == int(MessageID.BITFIELD):
            self.bitfield = payload
            return msg_id, payload

        if msg_id == int(MessageID.HAVE):
            if len(payload) >= 4:
                piece_index = int.from_bytes(payload[:4], "big")
                self.have.add(piece_index)
            else:
                pass # Malformed HAVE message
            return msg_id, payload

        return msg_id, payload

    def has_piece(self, idx: int) -> bool:
        """Return True if the peer appears to have piece idx.

        Checks explicit HAVE messages and bitfield (if present).
        """
        if idx in self.have:
            return True

        if self.bitfield:
            byte_index = idx // 8
            if byte_index < len(self.bitfield):
                bit_in_byte = 7 - (idx % 8)
                return ((self.bitfield[byte_index] >> bit_in_byte) & 1) == 1

        return False

    def available_pieces(self):
        """Return an iterable of piece indices this peer claims to have."""
        if self.bitfield:
            bits = []
            total_pieces = self.meta.num_pieces
            for idx in range(total_pieces):
                if self.has_piece(idx):
                    bits.append(idx)
            return bits

        return sorted(self.have)

    def close(self):
        if self.closed or self.writer is None:
            return

        self.writer.close()

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.writer.wait_closed())
        except RuntimeError:
            pass # No running loop (close called outside async context)

        self.closed = True