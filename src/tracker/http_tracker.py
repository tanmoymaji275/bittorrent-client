import aiohttp
# import urllib.parse
from typing import List, Tuple
from bencode import decode
from .utils import compact_to_peers

class HTTPTrackerClient:
    def __init__(self, torrent_meta, peer_id: bytes, port=6881):
        self.meta = torrent_meta
        self.peer_id = peer_id  # MUST be 20 bytes
        self.port = port

        # Use primary announce URL or fallback
        if torrent_meta.announce:
            self.url = torrent_meta.announce
        elif torrent_meta.announce_list:
            self.url = torrent_meta.announce_list[0][0]
        else:
            raise ValueError("No announce URL found in torrent")

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

        # URL-encode binary fields
        def pct_encode(b: bytes) -> str:
            # Correct percent-encoding for trackers: %HH per byte
            return ''.join(f'%{byte:02X}' for byte in b)

        encoded = {}
        for k, v in params.items():
            if isinstance(v, bytes):
                encoded[k] = pct_encode(v)
            else:
                encoded[k] = str(v)

        print("Sending info_hash:", encoded["info_hash"])

        async with aiohttp.ClientSession() as session:
            query = "&".join(f"{k}={v}" for k, v in encoded.items())
            full_url = f"{self.url}?{query}"

            print("Final announce URL:", full_url)

            async with session.get(full_url) as resp:
                data = await resp.read()

        root = decode(data).value

        failure = root.get(b"failure reason")
        if failure:
            msg = failure if isinstance(failure, bytes) else failure.value
            raise RuntimeError("Tracker error: " + msg.decode())

        peers_field = root.get(b"peers")

        if isinstance(peers_field, bytes) or hasattr(peers_field, "value"):
            blob = peers_field if isinstance(peers_field, bytes) else peers_field.value
            return self._compact_to_peers(blob)

        raise ValueError("Tracker returned invalid peer list")
