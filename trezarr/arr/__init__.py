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
        "sonarr.lan"                    -> "sonarr.lan"

    The bare host returned here is passed to ``pyarr.Sonarr(host=..., port=..., tls=...)``
    which itself reconstructs the URL using the separately-configured port and tls
    kwargs. Users sometimes paste a full URL into the host field by reflex; this
    helper makes that input shape forgiving without changing pyarr's call site.

    Args:
        host: Bare hostname/IP OR a full URL with scheme/port/path.

    Returns:
        The bare host string (no scheme, no port, no trailing path/slash).
    """
    # If no scheme is present, treat as a bare hostname/IP — return unchanged.
    if "://" not in host:
        return host
    parsed = urlparse(host)
    # parsed.hostname strips the port for us; fall back to a manual split on netloc
    # in the (defensive) case parsed.hostname returns None for malformed input.
    return parsed.hostname or parsed.netloc.split(":")[0]
