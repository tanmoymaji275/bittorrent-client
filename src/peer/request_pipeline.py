import struct
import asyncio
from .message_types import MessageID, BLOCK_LEN


class RequestPipeline:
    def __init__(self, peer_conn, piece_manager, pipeline_depth=5, block_timeout=10):
        self.peer = peer_conn
        self.pieces = piece_manager
        self.pipeline_depth = pipeline_depth
        self.block_timeout = block_timeout

    async def start(self):
        await self.peer.send(MessageID.INTERESTED)

        # Wait for unchoke
        while True:
            msg_id, payload = await self.peer.read_message()
            if msg_id == MessageID.UNCHOKE:
                break

        # Main loop — get new pieces until peer is no longer useful
        while True:
            # Stop immediately if torrent already done
            if self.pieces.all_pieces_done():
                return

            piece_index = await self.pieces.reserve_piece_for_peer(self.peer)

            if piece_index is None:
                # Might be because last pieces were completed by other peers
                if self.pieces.all_pieces_done():
                    return
                print("[Pipeline] No more pieces for this peer.")
                return

            ok = await self.download_piece(piece_index)

            if not ok:
                await self.pieces.release_piece(piece_index, self.peer)
                return

    # noinspection DuplicatedCode
    async def download_piece(self, idx):
        length = self.pieces.get_piece_length(idx)
        offset = 0
        pending = set()

        # Fill initial pipeline window
        while offset < length and len(pending) < self.pipeline_depth:
            blen = min(BLOCK_LEN, length - offset)
            payload = struct.pack(">III", idx, offset, blen)
            await self.peer.send(MessageID.REQUEST, payload)
            pending.add(offset)
            offset += blen

        # Process incoming blocks
        while not self.pieces.piece_complete(idx):

            # FAST EXIT: If torrent is fully done, stop immediately
            if self.pieces.all_pieces_done():
                return True

            try:
                msg_id, payload = await asyncio.wait_for(
                    self.peer.read_message(),
                    timeout=self.block_timeout
                )
            except asyncio.TimeoutError:
                print(f"[Pipeline] Block timeout for piece {idx}")
                return False

            if msg_id is None:
                print("[Pipeline] Peer closed connection.")
                return False

            if msg_id == MessageID.PIECE:
                got_idx = int.from_bytes(payload[0:4], "big")
                begin   = int.from_bytes(payload[4:8], "big")
                block   = payload[8:]

                if got_idx == idx:
                    await self.pieces.store_block(idx, begin, block)
                    if begin in pending:
                        pending.remove(begin)

                # Slide window when possible
                while offset < length and len(pending) < self.pipeline_depth:
                    blen = min(BLOCK_LEN, length - offset)
                    payload = struct.pack(">III", idx, offset, blen)
                    await self.peer.send(MessageID.REQUEST, payload)
                    pending.add(offset)
                    offset += blen

        print(f"[Pipeline] Completed piece {idx}")
        return True
