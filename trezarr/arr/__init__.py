"""Trezarr *arr discovery layer — Sonarr + Radarr API wrappers.

Module-level helpers:
  DiscoveryError      — raised by discover_sonarr_items / discover_radarr_items when the
                        underlying httpx / pyarr layer fails. cli.py (Plan 03-05) catches
                        this per-service to implement D-30-style per-service resilience
                        (one *arr down does not abort the run if the other is healthy).
  _normalize_arr_host — accepts bare hostnames or full URLs and returns the bare host.
                        pyarr's Sonarr/Radarr constructors expect a bare host string and
                        a separate port kwarg, so we strip any scheme/port/path the user
                        may have pasted into sonarr_host / radarr_host.

Per 03-REVIEWS.md MEDIUM #10 (typed DiscoveryError) and MEDIUM #15 (_normalize_arr_host).
"""
from __future__ import annotations

from urllib.parse import urlparse

__all__ = ["DiscoveryError", "_normalize_arr_host"]


class DiscoveryError(Exception):
    """Raised when an *arr discovery call fails at the HTTP transport layer.

    Wraps pyarr's `PyarrError` family (which itself wraps httpx.HTTPStatusError,
    httpx.RequestError, etc.) so callers (cli.py) can apply per-service resilience
    without depending on pyarr's internal exception hierarchy directly.
    """


def _normalize_arr_host(host: str) -> str:
    """Accept either a bare hostname/IP or a full URL; return the bare host.

    Examples::

        "192.168.1.10"                  -> "192.168.1.10"
        "http://192.168.1.10:8989"      -> "192.168.1.10"
        "https://sonarr.example/api"    -> "sonarr.example"
        "https://admin:hunter2@sonarr/" -> "sonarr"      (userinfo stripped — WR-01)
        "sonarr.lan"                    -> "sonarr.lan"
        "sonarr.lan:8989"               -> "sonarr.lan"  (bare host:port — WR-02)

    The bare host returned here is passed to ``pyarr.Sonarr(host=..., port=..., tls=...)``
    which itself reconstructs the URL using the separately-configured port and tls
    kwargs. Users sometimes paste a full URL into the host field by reflex; this
    helper makes that input shape forgiving without changing pyarr's call site.

    Per WR-01: this function is ALSO the log-redaction choke-point. Callers
    that include the *arr host in error messages MUST route the value through
    _normalize_arr_host first so any embedded `user:password@host` credentials
    are stripped before reaching logs / DiscoveryError messages.

    Per WR-02: a bare `host:port` shape (no scheme present, most common
    docker-compose convention) now strips the trailing `:NNN` — previously
    this case returned the raw input verbatim, producing a malformed URL like
    `http://sonarr.lan:8989:8989/api/...` when pyarr re-attached its `port=`
    kwarg.

    Args:
        host: Bare hostname/IP OR a full URL with scheme/port/path/userinfo.

    Returns:
        The bare host string (no scheme, no port, no userinfo, no trailing path/slash).
    """
    # Full URL form: urlparse handles scheme/userinfo/port stripping for us.
    if "://" in host:
        parsed = urlparse(host)
        # parsed.hostname strips the port AND userinfo for us; fall back to a
        # manual netloc split in the (defensive) case parsed.hostname returns
        # None for malformed input. The manual fallback intentionally splits on
        # both '@' (userinfo) and ':' (port) so it stays redaction-safe.
        if parsed.hostname:
            return parsed.hostname
        netloc = parsed.netloc
        # Strip userinfo if present (defensive — protect logs even on malformed input).
        if "@" in netloc:
            netloc = netloc.rsplit("@", 1)[-1]
        return netloc.split(":")[0]
    # Bare host shape, possibly with embedded port — strip any ":NNN" suffix (WR-02).
    if ":" in host:
        return host.split(":", 1)[0]
    return host
