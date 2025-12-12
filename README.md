# Asyncio BitTorrent Client

A high-performance, asynchronous BitTorrent client implementation in Python 3. It leverages `asyncio` for non-blocking I/O, enabling efficient concurrent peer connections, parallel tracker announcements, and pipelined block requests.

## Features

*   **Asynchronous I/O:** Built entirely on Python's `asyncio` for high concurrency.
*   **Fast Resume:** Starts downloading immediately as soon as the first peer connects.
*   **Parallel Tracker Scrapes:** Queries all trackers simultaneously to find peers quickly.
*   **Parallel Peer Connections:** Initiates multiple peer handshakes in parallel for fast swarm joining.
*   **Endgame Mode:** Parallelizes requests for the final few pieces to prevent "tail latency" delays.
*   **Pipelining:** Uses batched request pipelining (default depth: 50) to saturate TCP connections.
*   **Non-Blocking Disk I/O:** Offloads file writing/reading to a thread pool to keep the event loop responsive.
*   **Resume Capability:** Verifies existing files on startup and resumes partial downloads.
*   **Multi-Tracker Support:** Supports HTTP and UDP trackers.

## Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/tanmoymaji275/bittorrent-client.git
    cd bittorrent-client
    ```

2.  **Set up a virtual environment (recommended):**
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows: .venv\Scripts\activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install aiohttp
    ```

## Usage

1.  **Place a torrent file:**
    Put your `.torrent` file in the `torrents/` directory. By default, the client looks for `torrents/big-buck-bunny.torrent` (configurable in `main.py`).

2.  **Run the client:**
    ```bash
    python main.py
    ```

    The client will:
    *   Parse the torrent metadata.
    *   Contact trackers to get a list of peers.
    *   Connect to peers and start downloading to the `downloads/` directory.
    *   Display progress and logs in the terminal.

## Architecture

The project is structured into modular components:

*   **`main.py`**: Entry point. Sets up the event loop and orchestrates the session.
*   **`src/session_manager.py`**: Manages the download session, peer lifecycle, and pipelines.
*   **`src/pieces/piece_manager.py`**: Handles file I/O, piece tracking, and bitfield verification.
*   **`src/peer/`**: Contains peer protocol logic (handshake, messages) and the request pipeline.
*   **`src/tracker/`**: Clients for HTTP and UDP trackers.
*   **`src/bencode/`**: Utilities for parsing Bencoded data.

See `src/README.md` for a deeper dive into the code structure.

## Development

*   **Linting:**
    ```bash
    pylint src
    ```
*   **Testing:**
    ```bash
    pytest
    ```
