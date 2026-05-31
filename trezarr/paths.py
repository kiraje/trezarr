"""Path-mapping layer: PathMapping model + remote→local prefix substitution + guards.

This module is the lower layer in the trezarr dep graph — it must NOT import
from trezarr.config, so config.py can import PathMapping from here without
forming an import cycle.

Plan 03-02 Task 1 creates this file with the PathMapping pydantic model so
trezarr/config.py can declare `path_mappings: list[PathMapping]`. Plan 03-02
Task 2 extends this file with the rest of the path-mapping API
(apply_path_mapping, assert_within_media_roots, build_media_roots,
probe_media_roots, assert_media_roots_configured).
"""
from __future__ import annotations

from pydantic import BaseModel


class PathMapping(BaseModel):
    """A remote→local path prefix substitution pair (D-23).

    Defined as a pydantic BaseModel (not a dataclass) so pydantic-settings can
    deserialize the JSON array env var `TREZARR_PATH_MAPPINGS` and YAML
    `path_mappings:` lists into a list[PathMapping] field on TrezarrSettings.

    Attributes:
        remote: Prefix as it appears in *arr API-returned paths (e.g. "/tv").
        local:  Corresponding local path in this container / host (e.g. "/data/tv").
    """

    remote: str
    local: str
