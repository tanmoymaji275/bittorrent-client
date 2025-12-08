import asyncio
import struct
from .peer_protocol import build_handshake, parse_handshake, build_message


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
            resp = await self.reader.readexactly(68)    # pstrlen + pstr + reserved + info_hash + peer_id
        except asyncio.IncompleteReadError:
            raise ConnectionError("Peer closed connection during handshake")

        info_hash, remote_pid = parse_handshake(resp)
        self.remote_peer_id = remote_pid

        if info_hash != self.meta.info_hash:
            raise ValueError("Peer sent a handshake with wrong info_hash")

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
        """Reads and parses the next framed peer message."""
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

        return msg_id, payload

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