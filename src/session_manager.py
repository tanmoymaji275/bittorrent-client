import asyncio
from peer.peer_connection import PeerConnection
from peer.request_pipeline import RequestPipeline
from pieces.piece_manager import PieceManager

class SessionManager:
    def __init__(self, torrent_meta, peer_id, download_dir="."):
        self.tasks = None
        self.meta = torrent_meta
        self.peer_id = peer_id
        self.download_dir = download_dir

        # Shared piece manager for all peers
        self.piece_manager = PieceManager(self.meta, download_dir=self.download_dir)

        self.peers = []       # list of PeerConnection objects
        self.pipelines = []   # list of running RequestPipeline tasks

    async def add_peer(self, ip, port):
        """
        Create a PeerConnection, perform handshake,
        and store it in the session.
        """
        try:
            conn = PeerConnection(ip, port, self.meta, self.peer_id)
            await conn.connect()
            print(f"[Session] Connected to peer {ip}:{port}")

            self.peers.append(conn)
            return conn
        except Exception as e:
            print(f"[Session] Failed to connect to {ip}:{port} → {e}")
            return None

    async def start(self):
        print("[Session] Starting pipelines...")

        # Launch pipelines
        self.tasks = [
            asyncio.create_task(RequestPipeline(peer, self.piece_manager).start())
            for peer in self.peers
        ]

        # Monitor until download complete
        await self.monitor_until_done()

        print("[Session] Torrent download complete!")

        # Cancel all remaining tasks
        for t in self.tasks:
            t.cancel()

        # Close peers
        for peer in self.peers:
            peer.close()

    async def monitor_until_done(self):
        """
        Monitor piece completion. As soon as all pieces are downloaded,
        return immediately and cancel all pipelines.
        """
        while not self.piece_manager.all_pieces_done():
            await asyncio.sleep(0.1)
