import urllib.parse
# from typing import List, Tuple

from .http_tracker import HTTPTrackerClient
from .udp_tracker import UDPTrackerClient


class TrackerClient:
    def __init__(self, torrent_meta, peer_id: bytes, port=6881):
        self.meta = torrent_meta
        self.peer_id = peer_id  # MUST be 20 bytes
        self.port = port

        # Pick the best tracker URL
        if torrent_meta.announce:
            self.url = torrent_meta.announce
        elif torrent_meta.announce_list:
            self.url = torrent_meta.announce_list[0][0]
        else:
            raise ValueError("No announce URL found in torrent")

    def _scheme(self):
        return urllib.parse.urlparse(self.url).scheme.lower()

    async def announce(self):
        scheme = self._scheme()

        # Try HTTP(S) first if available
        if self.meta.announce_list:
            for tier in self.meta.announce_list:
                for url in tier:
                    parsed = urllib.parse.urlparse(url)
                    if parsed.scheme in ("http", "https"):
                        try:
                            client = HTTPTrackerClient(self.meta, self.peer_id, self.port)
                            client.url = url
                            return await client.announce()
                        except Exception as e:
                            print(f"[Tracker] HTTP tracker failed {url} → {e}")

        # If main announce is HTTP, use that
        if scheme in ("http", "https"):
            client = HTTPTrackerClient(self.meta, self.peer_id, self.port)
            try:
                return await client.announce()
            except Exception as e:
                print(f"[Tracker] HTTP announce failed → {e}")

        # LAST RESORT: UDP
        if scheme == "udp":
            client = UDPTrackerClient(self.meta, self.peer_id, self.port)
            try:
                return await client.announce()
            except Exception as e:
                print(f"[Tracker] UDP tracker timed out → {e}")

        raise RuntimeError("All trackers failed (HTTP + UDP).")

    # async def announce(self) -> List[Tuple[str, int]]:
    #     scheme = self._scheme()
    #
    #     if scheme in ("http", "https"):
    #         client = HTTPTrackerClient(self.meta, self.peer_id, self.port)
    #         return await client.announce()
    #
    #     if scheme == "udp":
    #         client = UDPTrackerClient(self.meta, self.peer_id, self.port)
    #         return await client.announce()
    #
    #     raise ValueError(f"Unsupported tracker scheme: {scheme}")
