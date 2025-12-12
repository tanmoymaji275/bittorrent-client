import asyncio
import struct

from .message_types import MessageID, BLOCK_LEN


# noinspection PyTypeChecker
class RequestPipeline:
    def __init__(self, peer_conn, piece_manager, pipeline_depth=50, block_timeout=10):
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
            if msg_id == MessageID.REQUEST:
                await self._handle_request(payload)

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

    async def _handle_request(self, payload):
        """Handle an incoming REQUEST message from the peer (Upload)."""
        if self.peer.am_choking:
            # We are choking them, so we ignore the request (Tit-for-Tat)
            return

        if len(payload) < 12:
            return

        index = int.from_bytes(payload[0:4], "big")
        begin = int.from_bytes(payload[4:8], "big")
        length = int.from_bytes(payload[8:12], "big")

        # Sanity check on length
        if length > 32 * 1024: 
            return

        block = await self.pieces.read_block(index, begin, length)
        if block:
            # Send PIECE message: index(4) + begin(4) + block
            resp_payload = payload[0:8] + block
            await self.peer.send(MessageID.PIECE, resp_payload)

    # noinspection DuplicatedCode
    async def download_piece(self, idx):
        length = self.pieces.get_piece_length(idx)
        offset = 0
        pending = set()

        # Fill initial pipeline window
        requests_sent = 0
        while offset < length and len(pending) < self.pipeline_depth:
            blen = min(BLOCK_LEN, length - offset)
            payload = struct.pack(">III", idx, offset, blen)
            await self.peer.send(MessageID.REQUEST, payload, drain=False)
            pending.add(offset)
            offset += blen
            requests_sent += 1
            
        if requests_sent > 0:
            await self.peer.writer.drain()

        # Get completion event for this piece (Endgame / Fast Cancel)
        piece_done_event = self.pieces.get_piece_event(idx)

        # Process incoming blocks
        while not self.pieces.piece_complete(idx):

            # FAST EXIT: If torrent is fully done, stop immediately
            if self.pieces.all_pieces_done():
                return True
                
            # If piece finished elsewhere (Endgame), stop immediately
            if piece_done_event.is_set():
                return True

            # Create tasks for reading message and waiting for piece completion
            read_task = asyncio.create_task(self.peer.read_message())
            event_task = asyncio.create_task(piece_done_event.wait())
            
            done, pending = await asyncio.wait(
                [read_task, event_task],
                return_when=asyncio.FIRST_COMPLETED,
                timeout=self.block_timeout
            )
            
            # Cancel pending tasks
            for t in pending:
                t.cancel()
                
            if not done:
                # Timeout occurred
                print(f"[Pipeline] Block timeout for piece {idx}")
                return False
                
            if event_task in done:
                # Piece finished by another peer
                return True
                
            # We got a message
            # noinspection PyBroadException
            try:
                msg_id, payload = read_task.result()
            except Exception:
                # Connection error or cancellation
                return False

            if msg_id is None:
                print("[Pipeline] Peer closed connection.")
                return False
                
            if msg_id == MessageID.REQUEST:
                await self._handle_request(payload)
                continue

            if msg_id == MessageID.PIECE:
                got_idx = int.from_bytes(payload[0:4], "big")
                begin   = int.from_bytes(payload[4:8], "big")
                block   = payload[8:]

                if got_idx == idx:
                    success = await self.pieces.store_block(idx, begin, block)
                    if not success:
                        return False

                    if begin in pending:
                        pending.remove(begin)

                # Slide window when possible
                requests_sent = 0
                while offset < length and len(pending) < self.pipeline_depth:
                    blen = min(BLOCK_LEN, length - offset)
                    payload = struct.pack(">III", idx, offset, blen)
                    await self.peer.send(MessageID.REQUEST, payload, drain=False)
                    pending.add(offset)
                    offset += blen
                    requests_sent += 1
                
                if requests_sent > 0:
                    await self.peer.writer.drain()

        print(f"[Pipeline] Completed piece {idx}")
        return True
