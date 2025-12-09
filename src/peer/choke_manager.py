import random
import asyncio
from typing import List
from .peer_connection import PeerConnection
from .message_types import MessageID
from .peer_scorer import PeerScorer

class ChokeManager:
    """
    Implements the Tit-for-Tat Choking algorithm with advanced reputation scoring.
    - Reciprocates uploads to the top 4 peers providing the best score (speed + stability).
    - Optimistically unchokes 1 random peer to discover new connections.
    """
    MIN_UPLOAD_PER_SLOT = 20 * 1024 # 20 KB/s target per peer
    MAX_SLOTS = 10 
    UPLOAD_MARGIN = 50 * 1024 # 50 KB/s safety margin above download speed

    def __init__(self, unchoke_slots=4):
        self.unchoke_slots = unchoke_slots
        self.optimistic_unchoke_peer = None
        self.optimistic_round_counter = 0
        self.scorer = PeerScorer()

    async def run_loop(self, peers_provider):
        """
        Periodically recalculates choking state for all peers.
        peers_provider: callable returning list of PeerConnection
        """
        while True:
            await asyncio.sleep(10)
            await self._recalculate(peers_provider())

    async def _recalculate(self, peers: List[PeerConnection]):
        # 1. Gather Stats from ALL peers (to calculate global rates)
        peer_data = [] # List of (peer, d_bytes, u_bytes, duration)
        total_upload = 0
        total_download = 0
        total_duration = 0
        
        for p in peers:
            d_bytes, u_bytes, duration = p.reset_stats()
            peer_data.append((p, d_bytes, u_bytes, duration))
            total_upload += u_bytes
            total_download += d_bytes
            total_duration += duration # Accumulate duration for global rate calculation
            
        # We calculate the average duration across peers, or default to 10s if no peers
        # The duration should be fairly consistent across all peers as they reset their stats
        # at the same time, but handling edge cases for safety.
        avg_duration = 10.0
        if peer_data and peer_data[0][3] > 0:
            avg_duration = peer_data[0][3]

        global_download_rate = total_download / avg_duration if avg_duration > 0 else 0
        
        # 2. Dynamic Slot Sizing (Download + Margin Strategy)
        # We limit our upload liability to roughly match our download speed plus a safety margin.
        allowed_upload_rate = global_download_rate + self.UPLOAD_MARGIN
        
        calculated_slots = int(allowed_upload_rate / self.MIN_UPLOAD_PER_SLOT)
        current_slots = max(2, calculated_slots) # Ensure at least 2 slots are always open.
        current_slots = min(current_slots, self.MAX_SLOTS)
            
        print(f"[ChokeManager] DL: {global_download_rate/1024:.1f} KB/s + Margin -> Slots: {current_slots}")

        # 3. Identify Interested Peers
        # Only peers interested in our data are considered for unchoking.
        interested_peers_data = [
            (p, d, u, t) for (p, d, u, t) in peer_data 
            if p.peer_interested and not p.closed
        ]
        
        if not interested_peers_data:
            return

        # 4. Score Peers (Reputation-Based Tit-for-Tat)
        # Peers are scored based on their download contribution, stability, and historical reliability.
        peers_with_score = []
        for p, d_bytes, u_bytes, duration in interested_peers_data:
            rate = d_bytes / duration if duration > 0 else 0
            score = self.scorer.score_peer(p, rate)
            peers_with_score.append((score, p))
        
        # Sort descending by score to identify the best partners.
        peers_with_score.sort(key=lambda x: x[0], reverse=True)
        sorted_peers = [p for _, p in peers_with_score]

        # 5. Select Top Peers to Unchoke
        top_peers = sorted_peers[:current_slots]
        unchoke_set = set(top_peers)

        # Reward the winners in the scoring system for future rounds.
        for p in top_peers:
            self.scorer.record_win(p)

        # 6. Handle Optimistic Unchoke (Every 3rd round, approx 30s interval)
        # This mechanism allows discovery of new, potentially faster, peers.
        self.optimistic_round_counter += 1
        if self.optimistic_round_counter >= 3:
            self.optimistic_round_counter = 0
            # Select candidates who are not already in the unchoke set.
            candidates = [p for _, p in peers_with_score if p not in unchoke_set]
            if candidates:
                self.optimistic_unchoke_peer = random.choice(candidates)
            else:
                self.optimistic_unchoke_peer = None

        if self.optimistic_unchoke_peer and self.optimistic_unchoke_peer.peer_interested:
             # Add optimistic peer to the unchoke set if they are interested.
             unchoke_set.add(self.optimistic_unchoke_peer)

        # 7. Apply Choke/Unchoke Decisions
        # Communicate the choking decisions to all peers.
        for p in peers:
            if p.closed: continue
            
            should_unchoke = p in unchoke_set
            
            if should_unchoke:
                if p.am_choking:
                    # Unchoke them if they are currently choked.
                    print(f"[ChokeManager] Unchoking {p.ip}")
                    await p.send(MessageID.UNCHOKE)
            else:
                if not p.am_choking:
                    # Choke them if they are currently unchoked and not selected.
                    print(f"[ChokeManager] Choking {p.ip}")
                    await p.send(MessageID.CHOKE)