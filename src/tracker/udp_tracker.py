import socket
import struct
import random
import urllib.parse
from typing import List, Tuple
from .utils import compact_to_peers


class UDPTrackerClient:
    def __init__(self, torrent_meta, peer_id: bytes, port=6881, timeout=5.0):
        self.meta = torrent_meta
        self.peer_id = peer_id  # MUST be 20 bytes
        self.port = port
        self.timeout = timeout

        if torrent_meta.announce:
            self.url = torrent_meta.announce
        elif torrent_meta.announce_list:
            self.url = torrent_meta.announce_list[0][0]
        else:
            raise ValueError("No announce URL found in torrent")

        parsed = urllib.parse.urlparse(self.url)
        self.host = parsed.hostname
        self.tracker_port = parsed.port or 80

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(self.timeout)

    @staticmethod
    def _compact_to_peers(blob: bytes) -> List[Tuple[str, int]]:
        return compact_to_peers(blob)

    def _send(self, data: bytes) -> bytes:
        self.sock.sendto(data, (self.host, self.tracker_port))
        return self.sock.recvfrom(4096)[0]

    async def announce(self) -> List[Tuple[str, int]]:
        protocol_id = 0x41727101980
        action = 0
        transaction_id = random.randint(0, 2**31 - 1)

        req = struct.pack(">QII", protocol_id, action, transaction_id)
        resp = self._send(req)

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

        resp = self._send(req)

        if len(resp) < 20:
            raise RuntimeError("Invalid UDP tracker announce response")

        action_res, trans_res, interval, leechers, seeders = struct.unpack(
            ">IIIII", resp[:20]
        )

        if trans_res != transaction_id or action_res != 1:
            raise RuntimeError("UDP announce failed")

        peers_blob = resp[20:]
        return self._compact_to_peers(peers_blob)
