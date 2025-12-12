"""
Implements peer scoring logic for the ChokeManager.
"""
import math


class PeerStats:
    """Stores and calculates statistics for a single peer's performance."""
    def __init__(self):
        self.ewma_rate = 0.0
        self.rate_history = []
        self.top_tier_count = 0
        
    def add_sample(self, rate, alpha=0.2, history_len=10):
        # Update Exponential Weighted Moving Average (EWMA)
        if self.ewma_rate == 0:
            self.ewma_rate = rate
        else:
            self.ewma_rate = (alpha * rate) + ((1 - alpha) * self.ewma_rate)
            
        self.rate_history.append(rate)
        if len(self.rate_history) > history_len:
            self.rate_history.pop(0)
            
    def get_variance_penalty(self):
        """Calculates a penalty factor (0.0 to 1.0) based on rate stability."""
        if len(self.rate_history) < 2:
            return 1.0 # No penalty if insufficient history
            
        mean = sum(self.rate_history) / len(self.rate_history)
        if mean == 0: 
            return 1.0 # Avoid division by zero, no penalty if mean is zero
            
        variance = sum((x - mean) ** 2 for x in self.rate_history) / len(self.rate_history)
        std_dev = math.sqrt(variance)
        
        # Coefficient of Variation (CV): A higher CV indicates greater instability.
        cv = std_dev / mean
        return 1.0 / (1.0 + cv)


class PeerScorer:
    """Calculates a comprehensive score for a peer based on performance and reliability."""
    def __init__(self):
        self.stats = {} # Maps peer objects to their PeerStats instances

    def get_stats(self, peer):
        """Retrieves or creates PeerStats for a given peer."""
        if peer not in self.stats:
            self.stats[peer] = PeerStats()
        return self.stats[peer]

    def record_win(self, peer):
        """Increments a peer's 'top_tier_count' when it's selected as a top uploader."""
        st = self.get_stats(peer)
        st.top_tier_count += 1

    def score_peer(self, peer, current_rate):
        """
        Calculates a comprehensive score for a peer based on current performance,
        historical consistency (EWMA & variance), and past reliability.
        """
        st = self.get_stats(peer)
        
        st.add_sample(current_rate)
        
        # Base Performance: Blend of current rate and smoothed historical average.
        base_performance = (0.7 * current_rate) + (0.3 * st.ewma_rate)
        
        # Stability: Apply a penalty if the peer's rate is highly variable.
        stability_factor = st.get_variance_penalty()
        
        # Trust: Apply a bonus based on how many times the peer has been a top contributor.
        trust_bonus = min(2.0, 1.0 + (st.top_tier_count * 0.01))
        
        # Final Score: Combine all factors.
        final_score = base_performance * stability_factor * trust_bonus
        
        return final_score
