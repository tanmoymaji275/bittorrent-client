import math

class PeerStats:
    def __init__(self):
        self.ewma_rate = 0.0
        self.rate_history = []  # Keep last N samples for variance
        self.top_tier_count = 0 # "Trust" counter
        
    def add_sample(self, rate, alpha=0.2, history_len=10):
        # Update EWMA
        if self.ewma_rate == 0:
            self.ewma_rate = rate
        else:
            self.ewma_rate = (alpha * rate) + ((1 - alpha) * self.ewma_rate)
            
        # Update History
        self.rate_history.append(rate)
        if len(self.rate_history) > history_len:
            self.rate_history.pop(0)
            
    def get_variance_penalty(self):
        if len(self.rate_history) < 2:
            return 1.0 # No penalty
            
        mean = sum(self.rate_history) / len(self.rate_history)
        if mean == 0: 
            return 1.0
            
        variance = sum((x - mean) ** 2 for x in self.rate_history) / len(self.rate_history)
        std_dev = math.sqrt(variance)
        
        # Coefficient of Variation (CV) = std_dev / mean
        # Higher CV means more unstable. 
        # We return a factor 0..1 to multiply the score by.
        # Example: if CV is 0 (perfectly stable), factor is 1.0
        # If CV is 1.0 (std_dev = mean), factor is 0.5
        cv = std_dev / mean
        return 1.0 / (1.0 + cv)

class PeerScorer:
    def __init__(self):
        self.stats = {} # Map peer_id -> PeerStats

    def get_stats(self, peer):
        if peer not in self.stats:
            self.stats[peer] = PeerStats()
        return self.stats[peer]

    def record_win(self, peer):
        """Call this when a peer makes it to the Top 4."""
        st = self.get_stats(peer)
        st.top_tier_count += 1

    def score_peer(self, peer, current_rate):
        st = self.get_stats(peer)
        
        # 1. Update internal stats
        st.add_sample(current_rate)
        
        # 2. Calculate Components
        
        # Base: 70% current speed, 30% historical average
        base_perf = (0.7 * current_rate) + (0.3 * st.ewma_rate)
        
        # Stability: Penalty for high variance
        stability_factor = st.get_variance_penalty()
        
        # Trust: 1% bonus for every time they were a top peer (capped at 2x)
        trust_bonus = min(2.0, 1.0 + (st.top_tier_count * 0.01))
        
        # Final Score
        final_score = base_perf * stability_factor * trust_bonus
        
        return final_score
