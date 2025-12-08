import struct
from .message_types import MessageID, BLOCK_LEN

class RequestPipeline:
    def __init__(self, peer_conn, piece_manager):
        self.peer = peer_conn
        self.pieces = piece_manager

    async def start(self):
        # Step 1: Tell peer we want pieces
        await self.peer.send(MessageID.INTERESTED)

        # Step 2: Wait for UNCHOKE
        while True:
            msg_id, payload = await self.peer.read_message()
            if msg_id == MessageID.UNCHOKE:
                break

        # Start downloading after unchoke
        await self.download_loop()

    async def download_loop(self):
        # choose a piece the peer actually has
        piece_index = self.pieces.get_piece_peer_has(self.peer)
        if piece_index is None:
            print("[Pipeline] Peer has no pieces we need.")
            return  # this peer is not useful for downloading now

        piece_length = self.pieces.get_piece_length(piece_index)

        # Request each block
        offset = 0
        while offset < piece_length:
            block_len = min(BLOCK_LEN, piece_length - offset)

            payload = struct.pack(">III", piece_index, offset, block_len)
            await self.peer.send(MessageID.REQUEST, payload)

            offset += block_len

        # Receive blocks until piece is complete
        while not self.pieces.piece_complete(piece_index):
            msg_id, payload = await self.peer.read_message()

            if msg_id is None:
                print("[Pipeline] Peer disconnected while downloading.")
                return

            if msg_id == MessageID.PIECE:
                idx = int.from_bytes(payload[0:4], "big")
                begin = int.from_bytes(payload[4:8], "big")
                block = payload[8:]
                await self.pieces.store_block(idx, begin, block)

        # Once done, move to next piece this peer has
        await self.download_loop()

    # async def download_loop(self):
    #     # Ask piece manager for next piece to download
    #     piece_index = self.pieces.get_next_piece()
    #     if piece_index is None:
    #         return  # download finished
    #
    #     piece_length = self.pieces.get_piece_length(piece_index)
    #
    #     # Request each block
    #     offset = 0
    #     while offset < piece_length:
    #         block_len = min(BLOCK_LEN, piece_length - offset)
    #
    #         # Build request payload: index, begin, length
    #         payload = struct.pack(">III", piece_index, offset, block_len)
    #         await self.peer.send(MessageID.REQUEST, payload)
    #
    #         offset += block_len
    #
    #     # Now receive blocks
    #     while not self.pieces.piece_complete(piece_index):
    #         msg_id, payload = await self.peer.read_message()
    #
    #         # Connection closed or error
    #         if msg_id is None:
    #             print("[Pipeline] Peer closed connection — breaking loop")
    #             return
    #
    #         if msg_id == MessageID.PIECE:
    #             # Parse PIECE message
    #             idx = int.from_bytes(payload[0:4], "big")
    #             begin = int.from_bytes(payload[4:8], "big")
    #             block = payload[8:]
    #
    #             await self.pieces.store_block(idx, begin, block)
    #
    #     # After finishing piece, start next one
    #     await self.download_loop()
