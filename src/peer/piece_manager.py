import hashlib
import os
from pathlib import Path
from .message_types import BLOCK_LEN


class PieceManager:
    def __init__(self, torrent_meta, download_dir="."):
        self.meta = torrent_meta
        self.download_dir = Path(download_dir)

        # Total pieces
        self.num_pieces = len(torrent_meta.pieces)

        # Track completed pieces
        self.completed = [False] * self.num_pieces

        # Temporary block storage: piece_idx → { offset: block_data }
        self.blocks = {i: {} for i in range(self.num_pieces)}

        # Precompute file offsets inside the *virtual* torrent
        self._compute_file_offsets()

        # Prepare output directories
        self._prepare_output_paths()

    # -------------------------------------------------------
    # Compute the global (virtual) offset for each file
    # -------------------------------------------------------
    def _compute_file_offsets(self):
        """Adds 'offset' field to each file dict inside TorrentMeta."""
        offset = 0
        for f in self.meta.files:
            f["offset"] = offset
            offset += f["length"]

    # -------------------------------------------------------
    # Create directories for multi-file torrents
    # -------------------------------------------------------
    def _prepare_output_paths(self):
        for f in self.meta.files:
            output_path = self.download_dir / f["path"]
            os.makedirs(output_path.parent, exist_ok=True)

    # -------------------------------------------------------
    # Piece selection
    # -------------------------------------------------------
    def get_next_piece(self):
        for i in range(self.num_pieces):
            if not self.completed[i]:
                return i
        return None

    # -------------------------------------------------------
    # Piece length
    # -------------------------------------------------------
    def get_piece_length(self, index):
        if index < self.num_pieces - 1:
            return self.meta.piece_length
        else:
            return self.meta.total_length - self.meta.piece_length * (self.num_pieces - 1)

    # -------------------------------------------------------
    # Store incoming block
    # -------------------------------------------------------
    async def store_block(self, piece_idx, offset, block):
        self.blocks[piece_idx][offset] = block

        if self.piece_complete(piece_idx):
            await self._finalize_piece(piece_idx)

    # -------------------------------------------------------
    # Check completeness
    # -------------------------------------------------------
    def piece_complete(self, piece_idx):
        piece_len = self.get_piece_length(piece_idx)
        offset = 0
        while offset < piece_len:
            if offset not in self.blocks[piece_idx]:
                return False
            offset += BLOCK_LEN
        return True

    # -------------------------------------------------------
    # Finalize piece: assemble, verify, write to disk
    # -------------------------------------------------------
    async def _finalize_piece(self, piece_idx):
        piece_len = self.get_piece_length(piece_idx)
        assembled = bytearray()

        # Assemble blocks
        offset = 0
        while offset < piece_len:
            assembled.extend(self.blocks[piece_idx][offset])
            offset += BLOCK_LEN

        # Verify hash
        expected = self.meta.pieces[piece_idx]
        actual = hashlib.sha1(assembled).digest()

        if expected != actual:
            print(f"[!] Piece {piece_idx} failed hash check — discarding")
            self.blocks[piece_idx].clear()
            return

        # Write verified piece to disk
        self._write_piece_to_disk(piece_idx, assembled)

        # Mark completed
        self.completed[piece_idx] = True
        self.blocks[piece_idx].clear()
        print(f"[✓] Piece {piece_idx} written")

    # -------------------------------------------------------
    # Write piece bytes into correct file(s)
    # -------------------------------------------------------
    def _write_piece_to_disk(self, piece_idx, piece_bytes):
        piece_start = piece_idx * self.meta.piece_length
        piece_len = len(piece_bytes)

        remaining = piece_len
        src_pos = 0

        for f in self.meta.files:
            f_start = f["offset"]
            f_end = f_start + f["length"]

            # Skip files before or after this piece
            if piece_start >= f_end or piece_start + piece_len <= f_start:
                continue

            # Calculate where in this file the piece overlaps
            write_start = max(0, piece_start - f_start)
            bytes_to_write = min(f_end - piece_start, remaining)

            out_path = self.download_dir / f["path"]

            # Open file
            with open(out_path, "r+b" if out_path.exists() else "wb") as fp:
                fp.seek(write_start)
                fp.write(piece_bytes[src_pos : src_pos + bytes_to_write])

            # Update counters
            src_pos += bytes_to_write
            remaining -= bytes_to_write

            if remaining <= 0:
                break
