
from bencode.decoder import decode
from bencode.encoder import encode
from bencode.structure import BencodeInt, BencodeString, BencodeList, BencodeDict


def test_int():
    print("Testing integer decoding...")
    obj = decode(b"i42e")
    print("Decoded:", obj)
    assert isinstance(obj, BencodeInt)
    assert obj.value == 42

    print("Testing integer encoding...")
    enc = encode(obj)
    print("Re-encoded:", enc)
    assert enc == b"i42e"


def test_string():
    print("Testing string decoding...")
    obj = decode(b"4:spam")
    print("Decoded:", obj)
    assert isinstance(obj, BencodeString)
    assert obj.value == b"spam"

    print("Testing string encoding...")
    assert encode(obj) == b"4:spam"


def test_list():
    print("Testing list decoding...")
    obj = decode(b"l4:spami3ee")
    print("Decoded:", obj)
    assert isinstance(obj, BencodeList)
    assert len(obj.value) == 2


def test_dict():
    print("Testing dictionary decoding & encoding...")
    obj = decode(b"d3:cow3:mooe")
    print("Decoded:", obj)
    assert isinstance(obj, BencodeDict)
    assert obj.value[b"cow"].value == b"moo"
    enc = encode(obj)
    print("Re-encoded:", enc)
    assert enc == b"d3:cow3:mooe"
