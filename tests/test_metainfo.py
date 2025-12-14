
from pathlib import Path

from torrent.metainfo import TorrentMeta


def test_metainfo_load():
    path = Path("torrents/sample.torrent")
    print("Loading torrent:", path)

    meta = TorrentMeta(path)
    print("Parsed TorrentMeta:", meta)

    assert meta.piece_length > 0
    assert len(meta.pieces) > 0
    assert meta.total_length > 0
    assert meta.announce is not None
    assert len(meta.files) >= 1

    print("Info hash:", meta.info_hash.hex())
    print("Files:", meta.files)
