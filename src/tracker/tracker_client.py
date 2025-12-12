import asyncio
from typing import List, Tuple

from .http_tracker import HTTPTrackerClient
from .udp_tracker import UDPTrackerClient


class TrackerClient:
    def __init__(self, torrent_meta, peer_id: bytes, port=6881):
        self.meta = torrent_meta
        self.peer_id = peer_id
        self.port = port

        self.trackers = []
        if self.meta.announce:
            self._add_tracker_client(self.meta.announce)
        
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

    async def _announce_one(self, client) -> List[Tuple[str, int]]:
        try:
            peers = await client.announce()
            print(f"[Tracker] {type(client).__name__} {client.url} returned {len(peers)} peers.")
            return peers
        except Exception as e:
            print(f"[Tracker] {type(client).__name__} {client.url} failed → {e}")
            return []

    async def announce(self) -> List[Tuple[str, int]]:
        all_peers = set()
        
        tasks = [self._announce_one(client) for client in self.trackers]
        results = await asyncio.gather(*tasks)
        
        for peer_list in results:
            for peer in peer_list:
                all_peers.add(peer)
        
        if not all_peers:
            raise RuntimeError("All trackers failed (HTTP + UDP).")
        
        return list(all_peers)
