import asyncio
import hashlib

import pytest

from peer.message_types import MessageID, BLOCK_LEN
from peer.request_pipeline import RequestPipeline
from pieces.piece_manager import PieceManager


# -----------------------------
# Fake Torrent Metadata
# -----------------------------
class FakeMeta:
    """
    Minimal fake torrent metadata for testing:
    - 1 piece
    - piece_length = BLOCK_LEN
    - SHA1 hash matches FakePeer block data (all zeros)
    """
    piece_length = BLOCK_LEN
    total_length = BLOCK_LEN
    files = [{"length": BLOCK_LEN, "path": "file.bin"}]

    raw_piece = bytes(BLOCK_LEN)  # FakePeer sends zeros
    pieces = [hashlib.sha1(raw_piece).digest()]


# -----------------------------
# Fake Peer Implementation
# -----------------------------
class FakePeer:
    """
    Simulates a peer that:
    - sends UNCHOKE once
    - responds to REQUEST messages with a single PIECE (one-piece torrent)
    - then closes when no more requests are coming
    """

    def __init__(self):
        self.sent_messages = []
        self.requests = asyncio.Queue()

        self.unchoked = False
        self.piece_sent = False
        self.writer = self

    async def drain(self):
        pass

    async def send(self, msg_id, payload=b"", drain=True):
        self.sent_messages.append((msg_id, payload))
        if msg_id == MessageID.REQUEST:
            # pipeline puts requests here; FakePeer will respond to them
            await self.requests.put(payload)

    async def read_message(self):
        # 1) First call â†’ UNCHOKE
        if not self.unchoked:
            self.unchoked = True
            return MessageID.UNCHOKE, None

        # 2) If there are pending requests, handle one (block until one arrives)
        if not self.requests.empty():
            req = await self.requests.get()
            print("[DEBUG FakePeer] Responding with PIECE")

            piece_idx = int.from_bytes(req[0:4], "big")
            begin = int.from_bytes(req[4:8], "big")
            length = int.from_bytes(req[8:12], "big")

            # Fake block matches FakeMeta (all zeros)
            block = bytes(length)

            payload = (
                piece_idx.to_bytes(4, "big") +
                begin.to_bytes(4, "big") +
                block
            )

            # mark that we've served the piece (test uses single-piece torrent)
            self.piece_sent = True
            return MessageID.PIECE, payload

        # 3) No pending requests:
        # If we've already sent the piece, return (None, None) to simulate close.
        # This lets RequestPipeline detect peer closed and finish cleanly.
        if self.piece_sent:
            print("[DEBUG FakePeer] No requests and piece already sent -> closing")
            return None, None

        # 4) Otherwise, block waiting for a request (no busy-loop, no recursion)
        # This will suspend until a REQUEST arrives.
        req = await self.requests.get()
        # handle it (same as above)
        piece_idx = int.from_bytes(req[0:4], "big")
        begin = int.from_bytes(req[4:8], "big")
        length = int.from_bytes(req[8:12], "big")
        block = bytes(length)
        payload = piece_idx.to_bytes(4, "big") + begin.to_bytes(4, "big") + block
        self.piece_sent = True
        return MessageID.PIECE, payload

    def has_piece(self, idx):
        return idx == 0

    def available_pieces(self):
        return [0]


# -----------------------------
# The actual test
# -----------------------------
@pytest.mark.asyncio
async def test_pipeline_download_fake_peer(tmp_path):
    """
    Tests that RequestPipeline:
    - waits for UNCHOKE
    - sends REQUESTs
    - receives PIECE blocks
    - stores them via PieceManager
    - writes final piece to disk
    """

    pm = PieceManager(FakeMeta(), download_dir=tmp_path)
    peer = FakePeer()

    pipeline = RequestPipeline(peer, pm)

    await pipeline.start()

    # ---------------------------------------
    # Assertions
    # ---------------------------------------

    # 1) Must send INTERESTED as first message
    assert peer.sent_messages[0][0] == MessageID.INTERESTED

    # 2) Must send at least one REQUEST
    assert any(m[0] == MessageID.REQUEST for m in peer.sent_messages)

    # 3) Piece should be marked as completed
    assert pm.completed[0] is True

    # 4) File must be written
    output_file = tmp_path / "file.bin"
    assert output_file.exists()
    assert output_file.stat().st_size == BLOCK_LEN
