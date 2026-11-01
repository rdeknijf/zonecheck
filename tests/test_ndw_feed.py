from __future__ import annotations

import gzip
import json
from datetime import UTC, datetime

import httpx
import pytest

from zonecheck import ndw_feed

URL = "https://opendata.ndw.nu/emissiezones.xml.gz"
T1 = datetime(2026, 11, 1, 6, 0, tzinfo=UTC)
T2 = datetime(2026, 11, 1, 7, 0, tzinfo=UTC)


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_gunzips_and_caches(tmp_path, zones_xml):
    raw = gzip.compress(zones_xml)

    def handler(request: httpx.Request) -> httpx.Response:
        assert "If-None-Match" not in request.headers
        return httpx.Response(
            200,
            content=raw,
            headers={"ETag": '"abc"', "Last-Modified": "Sun, 01 Nov 2026 05:10:10 GMT"},
        )

    snap = ndw_feed.fetch(URL, tmp_path, _client(handler), now=T1)
    assert snap.content == zones_xml
    assert snap.etag == '"abc"'
    assert snap.fetched_at == T1
    assert (tmp_path / "emissiezones.xml.gz").read_bytes() == raw
    meta = json.loads((tmp_path / "emissiezones.xml.gz.meta.json").read_text())
    assert meta["sha256"] == snap.sha256

    cached = ndw_feed.load_cached(URL, tmp_path)
    assert cached is not None
    assert cached.content == zones_xml


def test_not_modified_keeps_cached_copy(tmp_path, zones_xml):
    raw = gzip.compress(zones_xml)
    ndw_feed.fetch(
        URL,
        tmp_path,
        _client(lambda _: httpx.Response(200, content=raw, headers={"ETag": '"v1"'})),
        now=T1,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["If-None-Match"] == '"v1"'
        return httpx.Response(304)

    snap = ndw_feed.fetch(URL, tmp_path, _client(handler), now=T2)
    assert snap.content == zones_xml
    assert snap.fetched_at == T1
    assert snap.checked_at == T2
    assert snap.from_cache_after_error is None


def test_error_falls_back_to_cache(tmp_path, zones_xml):
    raw = gzip.compress(zones_xml)
    ndw_feed.fetch(
        URL, tmp_path, _client(lambda _: httpx.Response(200, content=raw)), now=T1
    )

    def broken(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    snap = ndw_feed.fetch(URL, tmp_path, _client(broken), now=T2)
    assert snap.content == zones_xml
    assert snap.from_cache_after_error == "down"


def test_error_without_cache_raises(tmp_path):
    with pytest.raises(ndw_feed.FeedError):
        ndw_feed.fetch(URL, tmp_path, _client(lambda _: httpx.Response(503)), now=T1)


def test_corrupt_gzip_without_cache_raises(tmp_path):
    bad = b"\x1f\x8b" + b"broken"
    with pytest.raises(ndw_feed.FeedError):
        ndw_feed.fetch(
            URL, tmp_path, _client(lambda _: httpx.Response(200, content=bad)), now=T1
        )


def test_plain_content_passes_through(tmp_path):
    snap = ndw_feed.fetch(
        "https://opendata.ndw.nu/plain.xml",
        tmp_path,
        _client(lambda _: httpx.Response(200, content=b"<x/>")),
        now=T1,
    )
    assert snap.content == b"<x/>"


@pytest.mark.parametrize(
    "url",
    ["http://opendata.ndw.nu/emissiezones.xml.gz", "https://example.com/x.xml.gz"],
)
def test_only_ndw_https(tmp_path, url):
    with pytest.raises(ValueError, match="not an NDW"):
        ndw_feed.fetch(url, tmp_path, _client(lambda _: httpx.Response(200)))


def test_unwritable_cache_raises_feed_error(tmp_path, zones_xml):
    blocker = tmp_path / "cache"
    blocker.write_text("a file, not a directory")
    with pytest.raises(ndw_feed.FeedError, match="cannot write the feed cache"):
        ndw_feed.fetch(
            URL,
            blocker,
            _client(lambda _: httpx.Response(200, content=gzip.compress(zones_xml))),
            now=T1,
        )
