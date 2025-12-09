import hashlib
from pathlib import Path
from bencode import *
import re


def extract_info_bytes(raw: bytes) -> bytes:
    """
    Extract the exact bencoded 'info' dictionary byte slice.
    This guarantees correct SHA-1 infohash as required by BitTorrent spec.
    """
    key = b"4:info"
    start = raw.index(key) + len(key)

    i = start

    def parse(idx):
        b = raw[idx:idx+1]

        # Integer: i123e
        if b == b"i":
            _end = raw.index(b"e", idx)
            return _end + 1

        # List: l ... e
        if b == b"l":
            idx += 1
            while raw[idx:idx+1] != b"e":
                idx = parse(idx)
            return idx + 1

        # Dict: d ... e
        if b == b"d":
            idx += 1
            while raw[idx:idx+1] != b"e":
                idx = parse(idx)  # key
                idx = parse(idx)  # value
            return idx + 1

        # String: len:value
        m = re.match(rb"(\d+):", raw[idx:])
        strlen = int(m.group(1))
        offset = idx + len(m.group(0))
        return offset + strlen

    end = parse(i)
    return raw[start:end]


class TorrentMeta:
    def __init__(self, path: Path):
        self.path = Path(path)

        # Load raw bytes
        raw = self.path.read_bytes()

        # ----------- NEW FIX: extract raw info bytes -----------
        self.info_bytes = extract_info_bytes(raw)
        self.info_hash = hashlib.sha1(self.info_bytes).digest()

        # Decode full torrent structure normally
        root = decode(raw)
        if not isinstance(root, BencodeDict):
            raise ValueError("Invalid torrent: root must be a dictionary")

        self.data = root.value

        # ------------------ INFO ------------------
        if b"info" not in self.data:
            raise ValueError("Torrent missing 'info' dictionary")

        info_b = self.data[b"info"]
        self.info = info_b.value

        # ------------------ NAME ------------------
        name_b = self.info.get(b"name")
        self.name = name_b.value.decode() if isinstance(name_b, BencodeString) else None

        # ------------------ ANNOUNCE URL ------------------
        ann_b = self.data.get(b"announce")
        self.announce = ann_b.value.decode() if isinstance(ann_b, BencodeString) else None

        # ------------------ ANNOUNCE-LIST ------------------
        self.announce_list = None
        ann_list_b = self.data.get(b"announce-list")

        if isinstance(ann_list_b, BencodeList):
            tiers = []
            for tier in ann_list_b.value:
                urls = []
                for u in tier.value:
                    if isinstance(u, BencodeString):
                        urls.append(u.value.decode())
                if urls:
                    tiers.append(urls)
            if tiers:
                self.announce_list = tiers

        # ------------------ PIECE LENGTH ------------------
        piece_len_b = self.info.get(b"piece length")
        self.piece_length = piece_len_b.value

        # ------------------ PIECES ------------------
        pieces_b = self.info.get(b"pieces")
        raw_pieces = pieces_b.value
        self.pieces = [raw_pieces[i:i+20] for i in range(0, len(raw_pieces), 20)]

        # ------------------ FILES ------------------
        if b"files" in self.info:
            self.files = []
            for f_entry in self.info[b"files"].value:
                entry = f_entry.value
                length_b = entry[b"length"]
                parts = [p.value.decode() for p in entry[b"path"].value]
                path = "/".join(parts)
                self.files.append({"length": length_b.value, "path": path})
        else:
            name_b = self.info[b"name"]
            length_b = self.info[b"length"]
            self.files = [{"length": length_b.value, "path": name_b.value.decode()}]

        self.total_length = sum(f["length"] for f in self.files)
        self.is_multi = b"files" in self.info
        self.is_single = not self.is_multi
        self.num_pieces = len(self.pieces)
        self.last_piece_length = (self.total_length % self.piece_length) or self.piece_length

        for f in self.files:
            f["abs_path"] = f"{self.name}/{f['path']}" if self.is_multi else self.name

    def __repr__(self):
        return (
            f"TorrentMeta(name={self.name!r}, files={len(self.files)}, pieces={self.num_pieces}, "
            f"multi={self.is_multi}, announce={self.announce!r})"
        )
