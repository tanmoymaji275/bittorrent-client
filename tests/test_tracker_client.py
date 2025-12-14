
import aiohttp
import pytest

from tracker.http_tracker import HTTPTrackerClient


class FakeResp:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc, val, tb):
        pass

    async def read(self):
        return b"d5:peers6:\x01\x02\x03\x04\x1A\xe1e"

class FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc, val, tb):
        pass

    def get(self, url, **kwargs):
        return FakeResp()

@pytest.mark.asyncio
async def test_tracker_mock(monkeypatch):
    monkeypatch.setattr(aiohttp, "ClientSession", lambda: FakeSession())

    class DummyMeta:
        info_hash = b"A"*20
        total_length = 100
        announce = "http://fake/announce"

    tc = HTTPTrackerClient(DummyMeta, peer_id=b"B" * 20)
    peers = await tc.announce()

    assert peers == [("1.2.3.4", 6881)]
