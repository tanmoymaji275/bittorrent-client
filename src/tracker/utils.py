from typing import List, Tuple

def compact_to_peers(blob: bytes) -> List[Tuple[str, int]]:
    peers = []
    for i in range(0, len(blob), 6):
        ip = ".".join(str(b) for b in blob[i:i+4])
        port = int.from_bytes(blob[i+4:i+6], "big")
        peers.append((ip, port))
    return peers
