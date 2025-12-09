import hashlib
import os
import asyncio
from pathlib import Path
from peer.message_types import BLOCK_LEN


class PieceManager:
    def __init__(self, torrent_meta, download_dir="."):
        self.meta = torrent_meta
        self.download_dir = Path(download_dir)

        self.num_pieces = len(torrent_meta.pieces)
        self.completed = [False] * self.num_pieces
        self.blocks = {i: {} for i in range(self.num_pieces)}

        # NEW: piece reservation system
        self.in_progress = {}           # piece_idx → peer
        self._lock = asyncio.Lock()

        self._compute_file_offsets()
        self._prepare_output_paths()

    # -------------------------- RESERVATION LOGIC --------------------------

    async def reserve_piece_for_peer(self, peer):
        """
        Reserve the first incomplete piece that the peer has and is not reserved or completed.
        Returns the index or None.
        """
        async with self._lock:
            for idx in range(self.num_pieces):
                if self.completed[idx]:
                    continue
                if idx in self.in_progress:
                    continue
                if peer.has_piece(idx):
                    self.in_progress[idx] = peer
                    return idx
        return None

    async def release_piece(self, idx, peer):
        """Release reservation if this peer was the owner."""
        async with self._lock:
            owner = self.in_progress.get(idx)
            if owner is peer or owner is None:
                self.in_progress.pop(idx, None)

    async def mark_piece_completed(self, idx):
        async with self._lock:
            self.completed[idx] = True
            self.in_progress.pop(idx, None)

    # -------------------------- BASIC METHODS --------------------------

    def get_piece_length(self, index):
        if index < self.num_pieces - 1:
            return self.meta.piece_length
        return self.meta.total_length - self.meta.piece_length * (self.num_pieces - 1)

    def piece_complete(self, idx):
        piece_len = self.get_piece_length(idx)
        offset = 0
        while offset < piece_len:
            if offset not in self.blocks[idx]:
                return False
            offset += BLOCK_LEN
        return True

    async def store_block(self, idx, offset, block):
        self.blocks[idx][offset] = block

        if self.piece_complete(idx):
            await self._finalize_piece(idx)

    async def _finalize_piece(self, idx):
        piece_len = self.get_piece_length(idx)
        assembled = bytearray()

        offset = 0
        while offset < piece_len:
            assembled.extend(self.blocks[idx][offset])
            offset += BLOCK_LEN

        expected = self.meta.pieces[idx]
        actual = hashlib.sha1(assembled).digest()

        if expected != actual:
            print(f"[!] Piece {idx} failed hash check — discarding")
            self.blocks[idx].clear()
            return

        self._write_piece_to_disk(idx, assembled)
        await self.mark_piece_completed(idx)
        self.blocks[idx].clear()
        print(f"[✓] Piece {idx} written")

    # -------------------------- FILE IO --------------------------

    def _compute_file_offsets(self):
        offset = 0
        for f in self.meta.files:
            f["offset"] = offset
            offset += f["length"]

    def _prepare_output_paths(self):
        for f in self.meta.files:
            output_path = self.download_dir / f["path"]
            os.makedirs(output_path.parent, exist_ok=True)

    def _write_piece_to_disk(self, idx, bytes_data):
        piece_start = idx * self.meta.piece_length
        remaining = len(bytes_data)
        src_pos = 0

        for f in self.meta.files:
            f_start = f["offset"]
            f_end   = f_start + f["length"]

            if piece_start >= f_end or piece_start + remaining <= f_start:
                continue

            write_start = max(0, piece_start - f_start)
            bytes_to_write = min(f_end - piece_start, remaining)

            out_path = self.download_dir / f["path"]
            with open(out_path, "r+b" if out_path.exists() else "wb") as fp:
                fp.seek(write_start)
                fp.write(bytes_data[src_pos: src_pos + bytes_to_write])

            src_pos += bytes_to_write
            remaining -= bytes_to_write
            if remaining <= 0:
                break

    def all_pieces_done(self):
        return all(self.completed)
