import socket
import struct
import threading

import pytest

from tracker.udp_tracker import UDPTrackerClient


def run_mock_udp_tracker(host, port, info_hash_expected, peer_id_expected):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((host, port))

    while True:
        data, addr = sock.recvfrom(2048)

        if len(data) >= 16:
            # CONNECT request
            protocol_id, action, trans_id = struct.unpack(">QII", data[:16])

            if action == 0:  # CONNECT
                connection_id = 0x1122334455667788
                resp = struct.pack(">IIQ", 0, trans_id, connection_id)
                sock.sendto(resp, addr)
                continue

            # ANNOUNCE request
            if action == 1:
                # connection_id = struct.unpack(">Q", data[:8])[0]
                _, trans_id = struct.unpack(">II", data[8:16])

                # parse info_hash and peer_id to validate
                info_hash = data[16:36]
                peer_id = data[36:56]

                assert info_hash == info_hash_expected
                assert peer_id == peer_id_expected

                interval = 1800
                leechers = 10
                seeders = 20

                # one mock peer: 127.0.0.1:6881  →  7F 00 00 01 1A E1
                peers = b"\x7F\x00\x00\x01" + (6881).to_bytes(2, "big")

                header = struct.pack(">IIIII", 1, trans_id, interval, leechers, seeders)
                sock.sendto(header + peers, addr)
                continue


def start_mock_tracker(info_hash, peer_id):
    host = "127.0.0.1"
    port = 9999  # free port for testing

    thread = threading.Thread(
        target=run_mock_udp_tracker,
        args=(host, port, info_hash, peer_id),
        daemon=True,
    )
    thread.start()
    return f"udp://{host}:{port}"


@pytest.mark.asyncio
async def test_udp_tracker_basic():
    _info_hash = b"A" * 20
    peer_id = b"-PC0001-ABCDEFGHIJKLMNOP"[:20]

    announce_url = start_mock_tracker(_info_hash, peer_id)

    class TorrentMetaMock:
        announce = announce_url
        announce_list = None
        info_hash = _info_hash
        total_length = 1234

    tracker = UDPTrackerClient(TorrentMetaMock, peer_id)

    peers = await tracker.announce()

    assert len(peers) == 1
    assert peers[0][0] == "127.0.0.1"
    assert peers[0][1] == 6881
