"""
Implements the BitTorrent HTTP Tracker Protocol.
"""
from typing import List, Tuple

import aiohttp

from bencode import decode
from bencode.structure import BencodeDict, BencodeList, BencodeInt, BencodeString
from .utils import compact_to_peers


class HTTPTrackerClient:
    """
    Communicates with an HTTP tracker to announce download status and retrieve peers.
    """
    def __init__(self, torrent_meta, peer_id: bytes, port=6881, url: str = None):
        self.meta = torrent_meta
        self.peer_id = peer_id
        self.port = port
        self.url = url if url else torrent_meta.announce

        if not self.url:
            raise ValueError("No announce URL provided for HTTPTrackerClient")

    @staticmethod
    def _compact_to_peers(blob: bytes) -> List[Tuple[str, int]]:
        return compact_to_peers(blob)

    async def announce(self) -> List[Tuple[str, int]]:
        params = {
            "info_hash": self.meta.info_hash,
            "peer_id": self.peer_id,
            "port": self.port,
            "uploaded": 0,
            "downloaded": 0,
            "left": self.meta.total_length,
            "compact": 1,
            "event": "started",
        }

        def pct_encode(b: bytes) -> str:
            return ''.join(f'%{byte:02X}' for byte in b)

        encoded = {}
        for k, v in params.items():
            if isinstance(v, bytes):
                encoded[k] = pct_encode(v)
            else:
                encoded[k] = str(v)

        async with aiohttp.ClientSession() as session:
            query = "&".join(f"{k}={v}" for k, v in encoded.items())
            full_url = f"{self.url}?{query}"

            async with session.get(full_url) as resp:
                data = await resp.read()

        root = decode(data).value

        failure = root.get(b"failure reason")
        if failure:
            msg = failure if isinstance(failure, bytes) else failure.value
            raise RuntimeError("Tracker error: " + msg.decode())

        peers_field = root.get(b"peers")

        if isinstance(peers_field, BencodeList):
            peers = []
            for peer_dict_b in peers_field.value:
                if isinstance(peer_dict_b, BencodeDict):
                    peer_dict = peer_dict_b.value
                    ip_b = peer_dict.get(b"ip")
                    port_b = peer_dict.get(b"port")

                    if isinstance(ip_b, BencodeString) and isinstance(port_b, BencodeInt):
                        peers.append((ip_b.value.decode(), port_b.value))
            return peers
        elif isinstance(peers_field, bytes) or (hasattr(peers_field, "value") and isinstance(peers_field.value, bytes)):
            blob = peers_field if isinstance(peers_field, bytes) else peers_field.value
            return self._compact_to_peers(blob)

        raise ValueError("Tracker returned invalid peer list")
