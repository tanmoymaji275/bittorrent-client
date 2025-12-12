import asyncio
from pathlib import Path
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from torrent.metainfo import TorrentMeta
from tracker.tracker_client import TrackerClient
from session_manager import SessionManager


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
    connect_future = asyncio.gather(*connect_tasks)

    # Race between session completion (download done) and connection attempts
    done, pending = await asyncio.wait(
        [session_task, connect_future],
        return_when=asyncio.FIRST_COMPLETED
    )

    # If session finished early (e.g. resume complete), cancel pending connections
    if session_task in done:
        if not connect_future.done():
            connect_future.cancel()
            try:
                await connect_future
            except asyncio.CancelledError:
                pass
    else:
        # Connections finished, now wait for session to complete
        await session_task


if __name__ == "__main__":
    asyncio.run(main())
