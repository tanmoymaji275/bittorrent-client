# Source Code Documentation

This directory contains the core logic of the BitTorrent client.

## Directory Structure

### `session_manager.py`
The central coordinator.
*   **`SessionManager`**: Initializes the `PieceManager`, `ChokeManager`, and manages the list of connected peers. It launches `RequestPipeline` tasks for each connected peer and monitors the overall download progress.

### `bencode/`
Handles the Bencoding serialization format used by BitTorrent.
*   **`decoder.py`**: Parses raw bytes into Python objects (dicts, lists, ints, bytes).
*   **`encoder.py`**: Serializes Python objects back into Bencoded bytes.
*   **`structure.py`**: Defines types like `BencodeDict`, `BencodeList`, etc.

### `peer/`
Manages networking and the Peer Wire Protocol.
*   **`peer_connection.py`**: Wraps an asyncio TCP connection. Handles the handshake, framing of messages (length-prefix), and basic send/receive logic.
*   **`peer_protocol.py`**: constants and helpers for building/parsing wire messages (choke, unchoke, have, piece, etc.).
*   **`request_pipeline.py`**: The "brain" of the download. It manages a sliding window of block requests for a specific peer, ensuring we keep the connection saturated (pipelining). It handles "Endgame Mode" logic to race for the final pieces.
*   **`choke_manager.py`**: Implements the Tit-for-Tat algorithm. It monitors peer speeds and decides which peers to unchoke (allow upload) and which to choke.

    ### Choke Algorithm (Custom Implementation)
    The client uses an advanced variant of the standard Tit-for-Tat strategy to maximize download speed and swarm health:
    
    1.  **Peer Scoring**: Peers are ranked not just by raw download speed, but by a composite score:
        *   **EWMA Rate**: Uses an Exponential Weighted Moving Average to smooth out speed fluctuations.
        *   **Stability Penalty**: Peers with highly variable speeds (high variance) receive a penalty score.
        *   **Trust Bonus**: Peers that have consistently been in the top tier over time receive a multiplier bonus (up to 2x), encouraging long-term relationships.
    
    2.  **Dynamic Slot Sizing**: Instead of a fixed number of upload slots, the client dynamically calculates slots based on the global download rate plus a safety margin (`50 KB/s`). This ensures we open enough slots to reciprocate the data we are receiving, without flooding the network if our download is slow.
    
    3.  **Optimistic Unchoke**: Every 3rd round (~30 seconds), one peer is randomly selected from the interested set (excluding current top peers) to be unchoked. This allows the client to discover new, potentially faster peers that were previously choked.

*   **`peer_scorer.py`**: Helper to score peers based on their download speed and reliability.

### `pieces/`
Handles data storage and integrity.
*   **`piece_manager.py`**: 
    *   Maps pieces to files on disk.
    *   Tracks which pieces are complete (`self.completed`).
    *   Handles **Non-Blocking I/O**: Runs file reads/writes in a thread pool to avoid blocking the asyncio event loop.
    *   **Reservation System**: Assigns pieces to peers using a "Rarest First" strategy. Supports multi-peer reservation for "Endgame Mode".

### `torrent/`
*   **`metainfo.py`**: Parses `.torrent` files. It extracts the SHA1 info hash (crucial for the handshake) and file layout (single vs. multi-file).

### `tracker/`
Communicates with trackers to find peers.
*   **`tracker_client.py`**: The high-level client that queries all available trackers (HTTP and UDP) in parallel (`asyncio.gather`) to aggregate a list of peers.
*   **`http_tracker.py`**: Implementation of the HTTP tracker protocol.
*   **`udp_tracker.py`**: Implementation of the UDP tracker protocol using `asyncio.DatagramProtocol`.

## Key Concepts

*   **Pipelining**: Instead of waiting for a block to arrive before requesting the next, we send a batch of requests (default 50) to keep the pipe full.
*   **Endgame Mode**: When all pieces are either downloaded or requested, we send requests for the remaining "in-progress" pieces to *all* available peers. The first one to deliver wins, and we cancel the others.
*   **Asyncio**: The entire application runs on a single event loop. Blocking operations (like disk I/O) are offloaded to threads, while network I/O is handled natively by asyncio.
