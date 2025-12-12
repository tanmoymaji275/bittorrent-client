import asyncio
from peer.peer_connection import PeerConnection
from peer.request_pipeline import RequestPipeline
from peer.choke_manager import ChokeManager
from pieces.piece_manager import PieceManager

class SessionManager:
    def __init__(self, torrent_meta, peer_id, download_dir="."):
        self.tasks = None
        self.meta = torrent_meta
        self.peer_id = peer_id
        self.download_dir = download_dir

        # Shared piece manager for all peers.
        # It's linked to the peers list for the Rarest-First strategy.
        self.piece_manager = PieceManager(self.meta, download_dir=self.download_dir)
        self.piece_manager.set_peers_provider(lambda: self.peers)

        self.peers = []       # list of PeerConnection objects
        self.pipelines = []   # list of running RequestPipeline tasks
        self.choke_manager = ChokeManager()

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
        # Verify existing data for resume
        self.piece_manager.verify_existing_data()

        print("[Session] Starting pipelines...")

        # Launch pipelines
        self.tasks = [
            asyncio.create_task(RequestPipeline(peer, self.piece_manager).start())
            for peer in self.peers
        ]
        
        # Start Choke Manager Loop
        self.tasks.append(
            asyncio.create_task(self.choke_manager.run_loop(lambda: self.peers))
        )

        try:
            # Monitor until download complete
            await self.monitor_until_done()

            print("[Session] Torrent download complete!")
        except asyncio.CancelledError:
            # Graceful shutdown on cancellation (Ctrl+C or outer task cancel)
            print("[Session] Cancelled. Shutting down gracefully...")
        finally:
            # Cancel all remaining tasks
            if self.tasks:
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
