from typing import List, Tuple
from .http_tracker import HTTPTrackerClient
from .udp_tracker import UDPTrackerClient


class TrackerClient:
    def __init__(self, torrent_meta, peer_id: bytes, port=6881):
        self.meta = torrent_meta
        self.peer_id = peer_id
        self.port = port

        self.trackers = []
        # Add primary announce URL
        if self.meta.announce:
            self._add_tracker_client(self.meta.announce)
        
        # Add trackers from announce-list
        if self.meta.announce_list:
            for tier in self.meta.announce_list:
                for url in tier:
                    self._add_tracker_client(url)

        if not self.trackers:
            raise ValueError("No announce URLs found in torrent")

    def _add_tracker_client(self, url: str):
        if url.startswith("http"):
            self.trackers.append(HTTPTrackerClient(self.meta, self.peer_id, self.port, url=url))
        elif url.startswith("udp"):
            self.trackers.append(UDPTrackerClient(self.meta, self.peer_id, self.port, url=url))
        # Add other protocols like ws:// for WebTorrent if needed

    async def announce(self) -> List[Tuple[str, int]]:
        all_peers = set()
        for tracker_client in self.trackers:
            try:
                peers = await tracker_client.announce()
                print(f"[Tracker] {type(tracker_client).__name__} {tracker_client.url} returned {len(peers)} peers.")
                for peer in peers:
                    all_peers.add(peer)
            except Exception as e:
                print(f"[Tracker] {type(tracker_client).__name__} {tracker_client.url} failed → {e}")
        
        if not all_peers:
            raise RuntimeError("All trackers failed (HTTP + UDP).")
        
        return list(all_peers)

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
