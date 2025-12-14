
from peer.message_types import MessageID
from peer.peer_protocol import build_handshake, parse_handshake, build_message, parse_message


def test_handshake_roundtrip():
    info_hash = b"A" * 20
    peer_id = b"B" * 20

    print("Building handshake...")
    hs = build_handshake(info_hash, peer_id)
    print("Handshake bytes:", hs)

    parsed_info, parsed_pid = parse_handshake(hs)
    print("Parsed handshake:", parsed_info, parsed_pid)

    assert parsed_info == info_hash
    assert parsed_pid == peer_id


def test_message_build_parse():
    print("Building REQUEST message...")
    msg = build_message(MessageID.INTERESTED)
    print("Message raw:", msg)

    parsed = parse_message(msg)
    print("Parsed:", parsed)

    assert parsed[0] == MessageID.INTERESTED
