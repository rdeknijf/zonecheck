"""Download and cache NDW open-data feeds (opendata.ndw.nu).

The module knows nothing about emission zones. It downloads one feed URL,
decompresses it when it is gzip, and keeps the last good copy on disk with
the HTTP validators, so that later feeds (charging tariffs, bridge openings)
can reuse it. Parsing belongs to the caller.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import zlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx

NDW_HOST = "opendata.ndw.nu"
_MAX_COMPRESSED_BYTES = 50 * 1024 * 1024
_MAX_DECOMPRESSED_BYTES = 500 * 1024 * 1024
_TIMEOUT = httpx.Timeout(60.0, connect=10.0)


class FeedError(RuntimeError):
    """The feed is not available, neither from NDW nor from the cache."""


@dataclass(frozen=True)
class FeedSnapshot:
    """One downloaded copy of a feed, already decompressed."""

    url: str
    content: bytes
    sha256: str
    fetched_at: datetime
    checked_at: datetime
    last_modified: str | None
    etag: str | None
    from_cache_after_error: str | None = None


def _validate_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != NDW_HOST:
        raise ValueError(f"not an NDW open-data HTTPS URL: {url}")
    return url


def _cache_paths(url: str, cache_dir: Path) -> tuple[Path, Path]:
    name = Path(urlparse(url).path).name or "feed"
    return cache_dir / name, cache_dir / f"{name}.meta.json"


def _decompress(raw: bytes) -> bytes:
    if raw[:2] != b"\x1f\x8b":
        return raw
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as handle:
        data = handle.read(_MAX_DECOMPRESSED_BYTES + 1)
    if len(data) > _MAX_DECOMPRESSED_BYTES:
        raise FeedError("decompressed feed exceeds the size limit")
    return data


def load_cached(url: str, cache_dir: Path) -> FeedSnapshot | None:
    """Return the cached copy of a feed, or None when there is none."""
    data_path, meta_path = _cache_paths(_validate_url(url), cache_dir)
    if not data_path.is_file() or not meta_path.is_file():
        return None
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    raw = data_path.read_bytes()
    content = _decompress(raw)
    return FeedSnapshot(
        url=url,
        content=content,
        sha256=hashlib.sha256(raw).hexdigest(),
        fetched_at=datetime.fromisoformat(meta["fetched_at"]),
        checked_at=datetime.fromisoformat(meta["checked_at"]),
        last_modified=meta.get("last_modified"),
        etag=meta.get("etag"),
    )


def _write_cache(
    url: str,
    cache_dir: Path,
    raw: bytes | None,
    *,
    fetched_at: datetime,
    checked_at: datetime,
    last_modified: str | None,
    etag: str | None,
    sha256: str,
) -> None:
    """Write the meta file, and the data file when raw is given."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    data_path, meta_path = _cache_paths(url, cache_dir)
    if raw is not None:
        tmp = data_path.with_suffix(data_path.suffix + ".tmp")
        tmp.write_bytes(raw)
        tmp.replace(data_path)
    meta = {
        "url": url,
        "fetched_at": fetched_at.isoformat(),
        "checked_at": checked_at.isoformat(),
        "last_modified": last_modified,
        "etag": etag,
        "sha256": sha256,
    }
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")


def fetch(
    url: str,
    cache_dir: Path,
    client: httpx.Client | None = None,
    *,
    now: datetime | None = None,
) -> FeedSnapshot:
    """Download a feed with a conditional GET and cache it.

    A 304 answer or a network error returns the cached copy. Without a cached
    copy a failed download raises FeedError.
    """
    _validate_url(url)
    now = now or datetime.now(UTC)
    cached = load_cached(url, cache_dir)
    headers: dict[str, str] = {}
    if cached is not None:
        if cached.etag:
            headers["If-None-Match"] = cached.etag
        if cached.last_modified:
            headers["If-Modified-Since"] = cached.last_modified

    own_client = client is None
    http = client or httpx.Client(timeout=_TIMEOUT, follow_redirects=False)
    try:
        response = http.get(url, headers=headers)
        if response.status_code == 304 and cached is not None:
            _write_cache(
                url,
                cache_dir,
                None,
                fetched_at=cached.fetched_at,
                checked_at=now,
                last_modified=cached.last_modified,
                etag=cached.etag,
                sha256=cached.sha256,
            )
            return FeedSnapshot(
                url=url,
                content=cached.content,
                sha256=cached.sha256,
                fetched_at=cached.fetched_at,
                checked_at=now,
                last_modified=cached.last_modified,
                etag=cached.etag,
            )
        response.raise_for_status()
        raw = response.content
        if len(raw) > _MAX_COMPRESSED_BYTES:
            raise FeedError("feed download exceeds the size limit")
        content = _decompress(raw)
    except (httpx.HTTPError, FeedError, OSError, EOFError, zlib.error) as exc:
        if cached is None:
            raise FeedError(f"cannot fetch {url} and no cached copy: {exc}") from exc
        return FeedSnapshot(
            url=url,
            content=cached.content,
            sha256=cached.sha256,
            fetched_at=cached.fetched_at,
            checked_at=cached.checked_at,
            last_modified=cached.last_modified,
            etag=cached.etag,
            from_cache_after_error=str(exc),
        )
    finally:
        if own_client:
            http.close()

    last_modified = response.headers.get("Last-Modified")
    etag = response.headers.get("ETag")
    sha256 = hashlib.sha256(raw).hexdigest()
    try:
        _write_cache(
            url,
            cache_dir,
            raw,
            fetched_at=now,
            checked_at=now,
            last_modified=last_modified,
            etag=etag,
            sha256=sha256,
        )
    except OSError as exc:
        raise FeedError(f"cannot write the feed cache in {cache_dir}: {exc}") from exc
    return FeedSnapshot(
        url=url,
        content=content,
        sha256=sha256,
        fetched_at=now,
        checked_at=now,
        last_modified=last_modified,
        etag=etag,
    )
