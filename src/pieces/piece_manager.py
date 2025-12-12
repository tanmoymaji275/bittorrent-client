import asyncio
import hashlib
import os
from pathlib import Path

from peer.message_types import BLOCK_LEN


# noinspection DuplicatedCode
class PieceManager:
    def __init__(self, torrent_meta, download_dir="."):
        self.meta = torrent_meta
        self.download_dir = Path(download_dir)

        self.num_pieces = len(torrent_meta.pieces)
        self.completed = [False] * self.num_pieces
        self.blocks = {i: {} for i in range(self.num_pieces)}

        # NEW: piece reservation system
        self.in_progress = {}           # piece_idx → set(peers)
        self.piece_events = {}          # piece_idx → asyncio.Event
        self._lock = asyncio.Lock()
        
        # Callback to access list of all peers (for Rarest-First)
        self.peers_provider = None

        self._compute_file_offsets()
        self._prepare_output_paths()

    def get_piece_event(self, idx):
        if idx not in self.piece_events:
            self.piece_events[idx] = asyncio.Event()
        return self.piece_events[idx]

    def verify_existing_data(self):
        """
        Scan existing files and verify pieces.
        Populate self.completed based on successful hash checks.
        """
        print("[PieceManager] Verifying existing data...")
        verified_count = 0
        
        for idx in range(self.num_pieces):
            piece_len = self.get_piece_length(idx)
            
            piece_data = bytearray()
            piece_start = idx * self.meta.piece_length
            remaining = piece_len
            
            # Read piece data from disk. This logic mirrors `read_block` but allows reading unverified pieces.
            for f in self.meta.files:
                f_start = f["offset"]
                f_end   = f_start + f["length"]

                if piece_start >= f_end or piece_start + remaining <= f_start:
                    continue
                
                read_abs_start = max(piece_start, f_start)
                read_abs_end = min(piece_start + remaining, f_end)
                
                read_count = read_abs_end - read_abs_start
                read_file_offset = read_abs_start - f_start
                
                out_path = self.download_dir / f["path"]
                
                if not out_path.exists():
                    piece_data = None
                    break
                
                try:
                    with out_path.open("rb") as fp:
                        fp.seek(read_file_offset)
                        chunk = fp.read(read_count)
                        if len(chunk) != read_count:
                            piece_data = None
                            break
                        piece_data.extend(chunk)
                except OSError:
                    piece_data = None
                    break
                
                piece_start += read_count
                remaining -= read_count
                if remaining <= 0:
                    break
            
            if piece_data and len(piece_data) == piece_len:
                actual_hash = hashlib.sha1(piece_data).digest()
                if actual_hash == self.meta.pieces[idx]:
                    self.completed[idx] = True
                    verified_count += 1
                    # print(f"[PieceManager] Piece {idx} verified.")
        
        print(f"[PieceManager] Verification complete. {verified_count}/{self.num_pieces} pieces available.")

    def set_peers_provider(self, provider_func):
        """
        Set a function that returns a list of current PeerConnection objects.
        Used to calculate piece rarity.
        """
        self.peers_provider = provider_func

    # -------------------------- RESERVATION LOGIC --------------------------

    async def reserve_piece_for_peer(self, peer):
        """
        Reserve a piece for the peer using Rarest-First strategy.
        Returns the piece index or None.
        """
        async with self._lock:
            # 1. Identify candidates: pieces this peer has, which we need (not done/reserved)
            candidates = []
            possible_pieces = peer.available_pieces()
            
            # Standard Pass: Find unreserved pieces
            for idx in possible_pieces:
                if self.completed[idx]:
                    continue
                if idx in self.in_progress:
                    continue
                candidates.append(idx)

            if candidates:
                # 2. If no peers_provider, fallback to picking the first available piece.
                if not self.peers_provider:
                    best_piece = candidates[0]
                else:
                    all_peers = self.peers_provider()
                    def get_frequency(piece_idx):
                        count = 0
                        for p in all_peers:
                            if p.has_piece(piece_idx):
                                count += 1
                        return count
                    candidates.sort(key=get_frequency)
                    best_piece = candidates[0]

                if best_piece not in self.in_progress:
                    self.in_progress[best_piece] = set()
                self.in_progress[best_piece].add(peer)
                return best_piece

            # Endgame Pass: Find in-progress pieces to help with
            endgame_candidates = []
            for idx in possible_pieces:
                if self.completed[idx]:
                    continue
                if idx in self.in_progress and peer not in self.in_progress[idx]:
                    endgame_candidates.append(idx)

            if endgame_candidates:
                # Pick the one with fewest peers (spread load)
                endgame_candidates.sort(key=lambda i: len(self.in_progress[i]))
                best_piece = endgame_candidates[0]
                self.in_progress[best_piece].add(peer)
                return best_piece
            
            return None

    async def release_piece(self, idx, peer):
        """Release reservation if this peer was working on it."""
        async with self._lock:
            if idx in self.in_progress:
                peers_set = self.in_progress[idx]
                peers_set.discard(peer)
                if not peers_set:
                    self.in_progress.pop(idx, None)

    async def mark_piece_completed(self, idx):
        async with self._lock:
            self.completed[idx] = True
            self.in_progress.pop(idx, None)
            if idx in self.piece_events:
                self.piece_events[idx].set()
                del self.piece_events[idx]

    # -------------------------- BASIC METHODS --------------------------

    def get_piece_length(self, index):
        if index < self.num_pieces - 1:
            return self.meta.piece_length
        return self.meta.total_length - self.meta.piece_length * (self.num_pieces - 1)

    def piece_complete(self, idx):
        if self.completed[idx]:
            return True
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
            return await self._finalize_piece(idx)
        return True

    async def _finalize_piece(self, idx):
        # Optimization: If another peer already finished it, return True
        if self.completed[idx]:
            return True

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
            return False

        self._write_piece_to_disk(idx, assembled)
        await self.mark_piece_completed(idx)
        self.blocks[idx].clear()
        print(f"[✓] Piece {idx} written")
        return True

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
            mode = "r+b" if out_path.exists() else "wb"
            with out_path.open(mode) as fp:
                fp.seek(write_start)
                fp.write(bytes_data[src_pos: src_pos + bytes_to_write])

            src_pos += bytes_to_write
            remaining -= bytes_to_write
            if remaining <= 0:
                break
                
    async def read_block(self, piece_idx, offset, length):
        """Read a block of data from disk for uploading (non-blocking)."""
        return await asyncio.to_thread(self._read_block_sync, piece_idx, offset, length)

    def _read_block_sync(self, piece_idx, offset, length):
        """Synchronous implementation of read_block to be run in a thread."""
        if not self.completed[piece_idx]:
            return None
            
        piece_start = piece_idx * self.meta.piece_length + offset
        remaining = length
        data = bytearray()
        
        for f in self.meta.files:
            f_start = f["offset"]
            f_end   = f_start + f["length"]

            # Check if this file overlaps with the requested range
            if piece_start >= f_end or piece_start + remaining <= f_start:
                continue
            
            # Calculate read bounds relative to this file
            # Intersection of [piece_start, piece_start + remaining] and [f_start, f_end]
            read_abs_start = max(piece_start, f_start)
            read_abs_end = min(piece_start + remaining, f_end)
            
            read_count = read_abs_end - read_abs_start
            read_file_offset = read_abs_start - f_start
            
            out_path = self.download_dir / f["path"]
            
            try:
                with out_path.open("rb") as fp:
                    fp.seek(read_file_offset)
                    chunk = fp.read(read_count)
                    if len(chunk) != read_count:
                        # File shorter than expected?
                        return None
                    data.extend(chunk)
            except OSError:
                return None
                
            remaining -= read_count
            # piece_start moves forward conceptually, but we used absolute calc
            # simpler: update piece_start to end of this read
            piece_start += read_count 
            
            if remaining <= 0:
                break
                
        if len(data) != length:
            return None
            
        return bytes(data)

    def all_pieces_done(self):
        return all(self.completed)
