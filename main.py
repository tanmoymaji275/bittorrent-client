import asyncio
import os
import sys
from pathlib import Path

sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.torrent.metainfo import TorrentMeta
from src.tracker.tracker_client import TrackerClient
from src.session_manager import SessionManager


async def main():
    torrent_path = Path("torrents/big-buck-bunny.torrent")
    meta = TorrentMeta(torrent_path)
    print("announce:", meta.announce)
    print("announce_list:", meta.announce_list)
    print("Computed info_hash:", meta.info_hash.hex())

    peer_id = b"-PC0001-123456abcdef"

    session = SessionManager(meta, peer_id, download_dir="downloads")


    tracker = TrackerClient(meta, peer_id)
    peers = await tracker.announce()

    print(f"[Main] Tracker returned {len(peers)} peers")

    # Start the session loop (verification, choke manager, monitoring)
    # This enables "fast resume" - downloading starts as soon as the first peer connects.
    session_task = asyncio.create_task(session.start())

    # Connect to peers in parallel
    connect_tasks = [
        session.add_peer(ip, port) 
        for ip, port in peers[:50]
    ]
    # We don't strictly need to wait for all connections to finish before continuing,
    # but we do need to keep the main loop alive.
    await asyncio.gather(*connect_tasks)

    # Wait for the download to complete
    await session_task


if __name__ == "__main__":
    asyncio.run(main())
