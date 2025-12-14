import pytest

from peer.choke_manager import ChokeManager
from peer.message_types import MessageID


class MockPeer:
    def __init__(self, ip, d_rate=0, u_rate=0):
        self.ip = ip
        self.peer_interested = True
        self.closed = False
        self.am_choking = True # Initially we are choking them
        
        # Simulated stats for a 10s interval
        self.d_bytes = d_rate * 10 
        self.u_bytes = u_rate * 10 
        self.duration = 10.0
        
        self.sent_messages = []

    def reset_stats(self):
        return self.d_bytes, self.u_bytes, self.duration
    
    def reset_download_stats(self):
         return self.d_bytes, self.duration

    async def send(self, msg_id, payload=b""):
        self.sent_messages.append(msg_id)
        if msg_id == MessageID.UNCHOKE:
            self.am_choking = False
        elif msg_id == MessageID.CHOKE:
            self.am_choking = True

@pytest.mark.asyncio
async def test_choke_manager_ranking():
    """
    Verify that peers are ranked by download speed and top N are unchoked.
    """
    cm = ChokeManager()

    # Create 6 peers with distinct download rates
    p1 = MockPeer("1", d_rate=1000, u_rate=20*1024)
    p2 = MockPeer("2", d_rate=800, u_rate=20*1024)
    p3 = MockPeer("3", d_rate=600, u_rate=20*1024)
    p4 = MockPeer("4", d_rate=400, u_rate=20*1024)
    p5 = MockPeer("5", d_rate=200, u_rate=0)
    p6 = MockPeer("6", d_rate=100, u_rate=0)

    peers = [p1, p2, p3, p4, p5, p6]

    # Run recalculate
    await cm._recalculate(peers)

    # Expect: p1, p2 UNCHOKED. (DL Rate: 3.0 KB/s + Margin: 50KB/s = 53KB/s. 53/20 = 2 slots)
    assert not p1.am_choking, f"p1 should be unchoked (Rate {p1.d_bytes})"
    assert not p2.am_choking
    
    assert p3.am_choking, "p3 should be choked"
    assert p4.am_choking, "p4 should be choked"
    assert p5.am_choking, "p5 should be choked"
    assert p6.am_choking, "p6 should be choked"

@pytest.mark.asyncio
async def test_dynamic_slots_increase():
    """
    Verify that higher global download rate (with margin) increases the number of slots.
    """
    cm = ChokeManager()

    # We want 7 slots. Need global_download_rate + UPLOAD_MARGIN >= 7 * 20KB/s = 140KB/s.
    # UPLOAD_MARGIN is 50KB/s, so global_download_rate needs to be >= 90KB/s.
    # For 7 peers, each needs d_rate >= 90KB/s / 7 = ~12.8 KB/s.
    peers = []
    for i in range(7):
        # Each peer contributes ~13.5KB/s to download rate
        p = MockPeer(str(i), d_rate=13500, u_rate=20*1024) 
        peers.append(p)
    
    await cm._recalculate(peers)

    unchoked_count = sum(1 for p in peers if not p.am_choking)
    assert unchoked_count == 7, f"Expected 7 slots for 140KB/s upload, got {unchoked_count}"

@pytest.mark.asyncio
async def test_dynamic_slots_decrease():
    """
    Verify that low global download rate (with margin) decreases slots to minimum (2).
    """
    cm = ChokeManager()

    # Global download very low (e.g. 1 KB/s total).
    # Allowed upload rate = 1 KB/s + 50 KB/s = 51 KB/s.
    # Slots = 51 / 20 = 2.
    peers = []
    for i in range(5):
        p = MockPeer(str(i), d_rate=100 + i, u_rate=100) # Tiny download contribution
        peers.append(p)

    await cm._recalculate(peers)

    unchoked_count = sum(1 for p in peers if not p.am_choking)
    assert unchoked_count == 2, f"Expected min 2 slots, got {unchoked_count}"

@pytest.mark.asyncio
async def test_optimistic_unchoke():
    """
    Verify that every 3rd round, an extra peer is unchoked.
    """
    cm = ChokeManager(unchoke_slots=2)

    # Global rate = 0. Slots = Min(2).
    # We have 10 peers. Top 2 get unchoked.
    # Round 3 -> Top 2 + 1 Optimistic = 3 unchoked.
    peers = [MockPeer(str(i), d_rate=1000-i*10, u_rate=0) for i in range(10)]

    # Round 1
    await cm._recalculate(peers)
    assert sum(1 for p in peers if not p.am_choking) == 2

    # Round 2
    await cm._recalculate(peers)
    assert sum(1 for p in peers if not p.am_choking) == 2

    # Round 3 (Optimistic!)
    await cm._recalculate(peers)

    # Should be 3 peers unchoked now
    unchoked = [p for p in peers if not p.am_choking]
    assert len(unchoked) == 3, "Round 3 should have 1 optimistic unchoke (2+1=3)"

    # Ensure the 3rd one is NOT one of the top 2 (p0, p1)
    # Actually p0, p1 are top by d_rate.
    # The optimistic one should be one of p2..p9.
    top_two = peers[:2]
    optimistic = [p for p in unchoked if p not in top_two]
    assert len(optimistic) == 1
    print(f"Optimistic peer was {optimistic[0].ip}")
