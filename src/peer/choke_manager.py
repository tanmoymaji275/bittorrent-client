import random
import asyncio
from typing import List
from .peer_connection import PeerConnection
from .message_types import MessageID

class ChokeManager:
    """
    Implements the Tit-for-Tat Choking algorithm.
    - Reciprocates uploads to the top 4 peers providing the best download rate.
    - Optimistically unchokes 1 random peer to discover new connections.
    """
    def __init__(self, unchoke_slots=4):
        self.unchoke_slots = unchoke_slots
        self.optimistic_unchoke_peer = None
        self.optimistic_round_counter = 0

    async def run_loop(self, peers_provider):
        """
        Periodically recalculates choking state for all peers.
        peers_provider: callable returning list of PeerConnection
        """
        while True:
            await asyncio.sleep(10)
            await self._recalculate(peers_provider())

    async def _recalculate(self, peers: List[PeerConnection]):
        # 1. Identify Interested Peers
        interested_peers = [p for p in peers if p.peer_interested and not p.closed]
        if not interested_peers:
            return

        # 2. Sort by Download Rate (Tit-for-Tat)
        # We read the rate, which also resets the counter for the next round
        peers_with_rate = []
        for p in interested_peers:
            rate = p.reset_download_stats()
            peers_with_rate.append((rate, p))
        
        # Sort descending by rate
        peers_with_rate.sort(key=lambda x: x[0], reverse=True)
        sorted_peers = [p for _, p in peers_with_rate]

        # 3. Select Top Peers to Unchoke
        unchoke_set = set(sorted_peers[:self.unchoke_slots])

        # 4. Handle Optimistic Unchoke (Every 3rd round = 30s)
        self.optimistic_round_counter += 1
        if self.optimistic_round_counter >= 3:
            self.optimistic_round_counter = 0
            candidates = [p for p in interested_peers if p not in unchoke_set]
            if candidates:
                self.optimistic_unchoke_peer = random.choice(candidates)
            else:
                self.optimistic_unchoke_peer = None

        if self.optimistic_unchoke_peer and self.optimistic_unchoke_peer in interested_peers:
            unchoke_set.add(self.optimistic_unchoke_peer)

        # 5. Apply Decisions
        # "peers" includes everyone, even those not interested. 
        # But we only change state for interested ones? 
        # Actually, spec says we can choke/unchoke anyone. 
        # Usually we default everyone else to CHOKED.
        
        for p in peers:
            if p.closed: continue
            
            should_unchoke = p in unchoke_set
            
            if should_unchoke:
                if p.am_choking:
                    # Unchoke them
                    print(f"[ChokeManager] Unchoking {p.ip}")
                    await p.send(MessageID.UNCHOKE)
            else:
                if not p.am_choking:
                    # Choke them
                    print(f"[ChokeManager] Choking {p.ip}")
                    await p.send(MessageID.CHOKE)
