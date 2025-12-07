import hashlib
from pathlib import Path
from ..bencode import *


class TorrentMeta:
    def __init__(self, path: Path):
        self.path = Path(path)

        # Decode .torrent file
        root = decode(self.path.read_bytes())
        if not isinstance(root, BencodeDict):
            raise ValueError("Invalid torrent: root must be a dictionary")

        self.data = root.value  # Python dict: keys=bytes, values=BencodeType

        # ------------------ INFO ------------------
        if b"info" not in self.data:
            raise ValueError("Torrent missing 'info' dictionary")

        info_b = self.data[b"info"]
        if not isinstance(info_b, BencodeDict):
            raise ValueError("'info' must be a dictionary")

        self.info = info_b.value  # Python dict (keys=bytes, values=BencodeType)

        # ------------------ INFO HASH ------------------
        self.info_bytes = encode(self.info)  # re-encoded EXACT info dict
        self.info_hash = hashlib.sha1(self.info_bytes).digest()

        # ------------------ ANNOUNCE URL ------------------
        self.announce = None
        ann_b = self.data.get(b"announce")
        if isinstance(ann_b, BencodeString):
            self.announce = ann_b.value.decode()

        # ------------------ ANNOUNCE-LIST ------------------
        self.announce_list = None
        ann_list_b = self.data.get(b"announce-list")

        if isinstance(ann_list_b, BencodeList):
            announce_list = []
            for tier in ann_list_b.value:
                if isinstance(tier, BencodeList):
                    urls = []
                    for u in tier.value:
                        if isinstance(u, BencodeString):
                            urls.append(u.value.decode())
                    if urls:
                        announce_list.append(urls)

            if announce_list:
                self.announce_list = announce_list

        # ------------------ PIECE LENGTH ------------------
        piece_len_b = self.info.get(b"piece length")
        if not isinstance(piece_len_b, BencodeInt):
            raise ValueError("Missing or invalid 'piece length' in 'info'")
        self.piece_length = piece_len_b.value

        # ------------------ PIECES ------------------
        pieces_b = self.info.get(b"pieces")
        if not isinstance(pieces_b, BencodeString):
            raise ValueError("Missing or invalid 'pieces' in 'info'")

        raw_pieces = pieces_b.value
        if len(raw_pieces) % 20 != 0:
            raise ValueError("'pieces' must be a multiple of 20 bytes")

        self.pieces = [
            raw_pieces[i:i + 20] for i in range(0, len(raw_pieces), 20)
        ]

        # ------------------ FILES ------------------
        if b"files" in self.info:
            # ========== MULTI-FILE TORRENT ==========
            files_b = self.info[b"files"]

            if not isinstance(files_b, BencodeList):
                raise ValueError("'files' must be a list")

            self.files = []
            for f_entry in files_b.value:
                if not isinstance(f_entry, BencodeDict):
                    raise ValueError("Each entry in 'files' must be a dict")

                entry = f_entry.value
                length_b = entry.get(b"length")
                path_b = entry.get(b"path")

                if not isinstance(length_b, BencodeInt):
                    raise ValueError("File entry missing 'length'")

                if not isinstance(path_b, BencodeList):
                    raise ValueError("'path' in file entry must be a list")

                # Path components MUST be BencodeString
                parts = []
                for p in path_b.value:
                    if not isinstance(p, BencodeString):
                        raise ValueError("Path components must be strings")
                    parts.append(p.value.decode())

                # TORRENT-SPEC PATH (always forward-slash)
                torrent_path = "/".join(parts)

                self.files.append({
                    "length": length_b.value,
                    "path": torrent_path
                })

        else:
            # ========== SINGLE-FILE TORRENT ==========
            name_b = self.info.get(b"name")
            length_b = self.info.get(b"length")

            if not isinstance(name_b, BencodeString):
                raise ValueError("Missing name for single-file torrent")

            if not isinstance(length_b, BencodeInt):
                raise ValueError("Missing length for single-file torrent")

            self.files = [{
                "length": length_b.value,
                "path": name_b.value.decode()
            }]

        # ------------------ TOTAL LENGTH ------------------
        self.total_length = sum(f["length"] for f in self.files)

    # ----------------------------------------------------
    # Utility for debugging
    # ----------------------------------------------------
    def __repr__(self):
        name = self.info[b"name"].value.decode()
        num_files = len(self.files)
        num_pieces = len(self.pieces)
        announce = self.announce or "<no announce>"

        return (
            f"TorrentMeta(name={name!r}, "
            f"files={num_files}, "
            f"pieces={num_pieces}, "
            f"announce={announce!r})"
        )