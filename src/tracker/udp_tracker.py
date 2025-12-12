"""
UDP Tracker Client implementation using asyncio DatagramProtocol.
"""
import asyncio
import random
import socket
import struct
import urllib.parse
from typing import List, Tuple, Optional

from .utils import compact_to_peers


class UDPTrackerProtocol(asyncio.DatagramProtocol):
    """
    A DatagramProtocol to handle UDP communication with a tracker.
    """
    def __init__(self, on_response_received: callable, on_timeout: callable):
        self.on_response_received = on_response_received
        self.on_timeout = on_timeout
        self.transport = None
        self.response_future = None

    def connection_made(self, transport):
        self.transport = transport
        pass

    def datagram_received(self, data, addr):
        if self.response_future and not self.response_future.done():
            self.response_future.set_result(data)
        self.on_response_received(data, addr)

    def error_received(self, exc):
        if self.response_future and not self.response_future.done():
            self.response_future.set_exception(exc)
        if self.transport:
            self.transport.close()

    def connection_lost(self, exc):
        if exc and self.response_future and not self.response_future.done():
            self.response_future.set_exception(exc)
        if self.transport:
            self.transport.close()

    async def send_and_receive(self, data: bytes, addr: Tuple[str, int], timeout: float) -> bytes:
        self.response_future = asyncio.get_running_loop().create_future()
        if self.transport:
            self.transport.sendto(data, addr)
            try:
                return await asyncio.wait_for(self.response_future, timeout=timeout)
            except asyncio.TimeoutError:
                self.on_timeout()
                raise
        else:
            raise RuntimeError("Transport not connected")


class UDPTrackerClient:
    """
    Communicates with a UDP tracker to announce download status and retrieve peers.
    """
    def __init__(self, torrent_meta, peer_id: bytes, port=6881, timeout=5.0, url: str = None):
        self.meta = torrent_meta
        self.peer_id = peer_id
        self.port = port
        self.timeout = timeout
        self.protocol: Optional[UDPTrackerProtocol] = None
        self.transport: Optional[asyncio.DatagramTransport] = None

        self.url = url if url else torrent_meta.announce
        if not self.url:
            if torrent_meta.announce_list:
                self.url = torrent_meta.announce_list[0][0]
            else:
                raise ValueError("No announce URL provided for UDPTrackerClient")

        parsed = urllib.parse.urlparse(self.url)
        self.host = parsed.hostname
        self.tracker_port = parsed.port or 80

        # Resolve IP to avoid WinError 10022 on Windows with asyncio UDP
        try:
            self.host_ip = socket.gethostbyname(self.host)
        except socket.error as e:
            print(f"[Tracker] Could not resolve {self.host}: {e}")
            self.host_ip = self.host

    @staticmethod
    def _compact_to_peers(blob: bytes) -> List[Tuple[str, int]]:
        return compact_to_peers(blob)

    async def _create_endpoint(self):
        loop = asyncio.get_running_loop()
        self.transport, self.protocol = await loop.create_datagram_endpoint(
            lambda: UDPTrackerProtocol(self._on_response, self._on_timeout),
            local_addr=('0.0.0.0', 0)
        )

    def _on_response(self, data: bytes, addr: Tuple[str, int]):
        pass

    def _on_timeout(self):
        print(f"[Tracker] UDP tracker request timed out")

    async def announce(self) -> List[Tuple[str, int]]:
        if not self.transport:
            await self._create_endpoint()

        protocol_id = 0x41727101980
        action = 0
        transaction_id = random.randint(0, 2**31 - 1)

        req = struct.pack(">QII", protocol_id, action, transaction_id)

        try:
            resp = await self.protocol.send_and_receive(req, (self.host_ip, self.tracker_port), self.timeout)
        except asyncio.TimeoutError:
            raise RuntimeError("UDP tracker connect timed out")

        if len(resp) < 16:
            raise RuntimeError("Invalid UDP tracker connect response")

        action_res, trans_res, connection_id = struct.unpack(">IIQ", resp[:16])

        if trans_res != transaction_id or action_res != 0:
            raise RuntimeError("UDP tracker connect failed")

        action = 1
        transaction_id = random.randint(0, 2**31 - 1)
        downloaded = 0
        left = self.meta.total_length
        uploaded = 0
        event = 2

        req = struct.pack(
            ">QII20s20sQQQIIIiH",
            connection_id,
            action,
            transaction_id,
            self.meta.info_hash,
            self.peer_id,
            downloaded,
            left,
            uploaded,
            event,
            0,
            random.randint(0, 2**31 - 1),
            -1,
            self.port,
        )

        try:
            resp = await self.protocol.send_and_receive(req, (self.host_ip, self.tracker_port), self.timeout)
        except asyncio.TimeoutError:
            raise RuntimeError("UDP tracker announce timed out")

        if len(resp) < 20:
            raise RuntimeError("Invalid UDP tracker announce response")

        action_res, trans_res, interval, leechers, seeders = struct.unpack(
            ">IIIII", resp[:20]
        )

        if trans_res != transaction_id or action_res != 1:
            raise RuntimeError("UDP announce failed")

        peers_blob = resp[20:]
        return self._compact_to_peers(peers_blob)