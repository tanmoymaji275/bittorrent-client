import asyncio
from pathlib import Path
import sys
import os

# Add src to sys.path so submodules can import 'bencode' as a top-level package
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.torrent.metainfo import TorrentMeta
from src.tracker.tracker_client import TrackerClient
from src.session_manager import SessionManager


async def main():
    torrent_path = Path("torrents/a.torrent")
    meta = TorrentMeta(torrent_path)
    print("announce:", meta.announce)
    print("announce_list:", meta.announce_list)
    print("Computed info_hash:", meta.info_hash.hex())

    peer_id = b"-PC0001-123456abcdef"

    session = SessionManager(meta, peer_id, download_dir="downloads")


    tracker = TrackerClient(meta, peer_id)
    peers = await tracker.announce()

    print(f"[Main] Tracker returned {len(peers)} peers")

    for ip, port in peers[:20]:
        await session.add_peer(ip, port)

    await session.start()


if __name__ == "__main__":
    asyncio.run(main())
