"""
Bencode package for encoding and decoding BitTorrent data.
"""
from .decoder import decode
from .encoder import encode
from .structure import BencodeDict, BencodeInt, BencodeList, BencodeString

__all__ = ['decode', 'encode', 'BencodeInt', 'BencodeString', 'BencodeList', 'BencodeDict']