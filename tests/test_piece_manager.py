import asyncio
import hashlib
from pathlib import Path

from peer.message_types import BLOCK_LEN
from pieces.piece_manager import PieceManager
from torrent.metainfo import TorrentMeta


async def fake_piece_download(pm):
    class DummyPeer:
        def has_piece(self, idx): return True
        def available_pieces(self): return range(pm.num_pieces)

    peer = DummyPeer()
    idx = await pm.reserve_piece_for_peer(peer)
    if idx is None: return

    piece_len = pm.get_piece_length(idx)

    offset = 0
    while offset < piece_len:
        block_len = min(BLOCK_LEN, piece_len - offset)
        await pm.store_block(idx, offset, b"\x00" * block_len)
        offset += block_len


def test_piece_manager():
    meta = TorrentMeta(Path("torrents/sample.torrent"))
    pm = PieceManager(meta, download_dir="downloads_test")

    # Fix expected hash for testing:
    piece_len = pm.get_piece_length(0)
    pm.meta.pieces[0] = hashlib.sha1(b"\x00" * piece_len).digest()

    asyncio.run(fake_piece_download(pm))

    assert pm.completed[0] is True
