"""Bible REST API — GET/PATCH/POST/DELETE /api/series, /api/series/{id}/bible, etc. (BIBLE-08).

Design decisions honoured:
  D-79  locked_fields JSON array on entity rows — no bible_lock table.
  D-80  apply_human_edit_* writers: one txn, in-txn re-read, locked_fields reassignment, BibleEvent.
  D-81  Per-series asyncio.Lock (get_series_lock) serializes UI writes with Pass-1 inference.
  D-82  load_field_history: read-only bible_event query, LIMIT 100.
  D-83  No character delete endpoint; address-pair and term DELETE via store functions only.
  D-87  PATCH address-map: HTTP 422 when lock=True and either term is empty/whitespace.
  D-88  No relationship-event authoring; event list is read-only display only.
  D-39  Routes receive/return Pydantic DTOs only — no SQLAlchemy models imported here.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter()

# Allowlist for entity_type in the history endpoint (T-08-04 — prevents arbitrary table scan).
VALID_ENTITY_TYPES: frozenset[str] = frozenset(
    {"character", "term_dictionary", "series", "address_map"}
)


def _get_session_factory(request: Request):
    """Return the async session_factory from app.state, or None in tests without lifespan."""
    try:
        return request.app.state.session_factory
    except AttributeError:
        return None


# ── GET /api/series ───────────────────────────────────────────────────────────────


@router.get("/series")
async def get_series_list(request: Request) -> JSONResponse:
    """BIBLE-08 c1: Return bounded list of all series (LIMIT 500 per T-08-02).

    Returns an empty list when the DB is not configured (no lifespan/no DB).
    """
    session_factory = _get_session_factory(request)
    if session_factory is None:
        return JSONResponse([])
    from trezarr.bible.store import load_all_series  # noqa: PLC0415

    dtos = await load_all_series(session_factory)
    return JSONResponse([d.model_dump(by_alias=True) for d in dtos])


# ── GET /api/series/{id}/bible ────────────────────────────────────────────────────


@router.get("/series/{series_id}/bible")
async def get_series_bible(series_id: int, request: Request) -> JSONResponse:
    """BIBLE-08 c1: Return the full SeriesBibleDTO for a series (by_alias=True for CR-02 register alias)."""
    session_factory = _get_session_factory(request)
    if session_factory is None:
        raise HTTPException(status_code=404, detail="Series not found")
    from trezarr.bible.store import load_series_bible  # noqa: PLC0415

    try:
        dto = await load_series_bible(session_factory, series_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Series not found")
    return JSONResponse(dto.model_dump(by_alias=True))


# ── PATCH /api/series/{id}/characters/{cid} ───────────────────────────────────────


@router.patch("/series/{series_id}/characters/{character_id}")
async def patch_character(
    series_id: int, character_id: int, request: Request
) -> JSONResponse:
    """D-81 / BIBLE-08 c2: Edit and optionally lock a character field.

    Field validation runs before any store call (T-08-01 defence). Series lock
    (D-81) is the outermost context manager wrapping the full store write.
    """
    body = await request.json()
    # T-08-01: validate field against whitelist BEFORE touching DB or acquiring lock
    from trezarr.bible.store import MERGEABLE_FIELDS  # noqa: PLC0415

    field = body.get("field")
    if field not in MERGEABLE_FIELDS.get("character", frozenset()):
        raise HTTPException(
            status_code=422, detail=f"Field '{field}' is not editable for character."
        )

    session_factory = _get_session_factory(request)
    if session_factory is None:
        raise HTTPException(status_code=503, detail="No DB session available")

    from trezarr.web.worker import get_series_lock  # noqa: PLC0415
    from trezarr.bible.store import apply_human_edit_character  # noqa: PLC0415

    async with get_series_lock(series_id):  # D-81: outermost CM
        try:
            dto, _evt = await apply_human_edit_character(
                session_factory,
                character_id=character_id,
                series_id=series_id,
                field=field,
                new_value=body.get("value"),
                lock=body.get("lock", False),
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
    return JSONResponse(dto.model_dump(by_alias=True))


# ── POST /api/series/{id}/characters ──────────────────────────────────────────────


@router.post("/series/{series_id}/characters")
async def add_character(series_id: int, request: Request) -> JSONResponse:
    """Add a character to the series Bible via upsert_character."""
    session_factory = _get_session_factory(request)
    if session_factory is None:
        raise HTTPException(status_code=503, detail="No DB session available")

    body = await request.json()
    from trezarr.bible.store import upsert_character  # noqa: PLC0415

    dto, _events = await upsert_character(
        session_factory,
        series_id=series_id,
        original_latin_name=body["original_latin_name"],
        gender=body.get("gender"),
        rough_age=body.get("rough_age"),
        role=body.get("role"),
        source=body.get("source", "import"),
    )
    return JSONResponse(dto.model_dump(by_alias=True))


# ── PATCH /api/series/{id}/address-map/{aid} ─────────────────────────────────────


@router.patch("/series/{series_id}/address-map/{address_map_id}")
async def patch_address_map(
    series_id: int, address_map_id: int, request: Request
) -> JSONResponse:
    """D-87 / BIBLE-08 c2: Edit and optionally lock an address-map pair.

    HTTP 422 if lock=True and either term is empty/whitespace (D-87 HTTP layer).
    Series lock (D-81) is the outermost context manager.
    """
    body = await request.json()
    self_term = body.get("self_term")
    address_term = body.get("address_term")
    lock = body.get("lock", False)

    # D-87 HTTP-layer guard: reject lock=True with empty/whitespace terms
    if lock:
        if not self_term or not str(self_term).strip():
            raise HTTPException(
                status_code=422,
                detail="Both self_term and address_term must be non-empty before locking a pair",
            )
        if not address_term or not str(address_term).strip():
            raise HTTPException(
                status_code=422,
                detail="Both self_term and address_term must be non-empty before locking a pair",
            )

    session_factory = _get_session_factory(request)
    if session_factory is None:
        raise HTTPException(status_code=503, detail="No DB session available")

    from trezarr.web.worker import get_series_lock  # noqa: PLC0415
    from trezarr.bible.store import apply_human_edit_address_pair  # noqa: PLC0415

    async with get_series_lock(series_id):  # D-81: outermost CM
        try:
            dto, _events = await apply_human_edit_address_pair(
                session_factory,
                address_map_id=address_map_id,
                series_id=series_id,
                self_term=self_term,
                address_term=address_term,
                lock=lock,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
    return JSONResponse(dto.model_dump(by_alias=True))


# ── POST /api/series/{id}/address-map ────────────────────────────────────────────


@router.post("/series/{series_id}/address-map")
async def add_address_pair(series_id: int, request: Request) -> JSONResponse:
    """Add an address-map pair via upsert_address_pair (D-83 FK: requires integer character IDs)."""
    session_factory = _get_session_factory(request)
    if session_factory is None:
        raise HTTPException(status_code=503, detail="No DB session available")

    body = await request.json()
    from trezarr.bible.store import upsert_address_pair  # noqa: PLC0415

    dto, _events = await upsert_address_pair(
        session_factory,
        series_id=series_id,
        speaker_character_id=int(body["speaker_character_id"]),
        addressee_character_id=int(body["addressee_character_id"]),
        self_term=body.get("self_term"),
        address_term=body.get("address_term"),
        valid_from_episode=body.get("valid_from_episode"),
        episode_key=body.get("episode_key"),
        source=body.get("source", "import"),
    )
    return JSONResponse(dto.model_dump(by_alias=True))


# ── DELETE /api/series/{id}/address-map/{aid} ────────────────────────────────────


@router.delete("/series/{series_id}/address-map/{address_map_id}")
async def delete_address_map(
    series_id: int, address_map_id: int, request: Request
) -> JSONResponse:
    """D-83: Delete an AddressMap leaf row via store function (D-39: no inline SQLAlchemy)."""
    session_factory = _get_session_factory(request)
    if session_factory is None:
        raise HTTPException(status_code=404, detail="Address pair not found")

    from trezarr.bible.store import delete_address_pair  # noqa: PLC0415

    try:
        result = await delete_address_pair(
            session_factory,
            address_map_id=address_map_id,
            series_id=series_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return JSONResponse(result)


# ── PATCH /api/series/{id}/terms/{tid} ───────────────────────────────────────────


@router.patch("/series/{series_id}/terms/{term_id}")
async def patch_term(series_id: int, term_id: int, request: Request) -> JSONResponse:
    """D-80 / BIBLE-08 c2: Edit and optionally lock a term field.

    CR-02: The URL term_id path parameter is the authoritative identity key — the store
    looks up the term by PK (term_id) scoped to series_id. Any source_term in the body
    is ignored (preventing cross-term writes via a mismatched body identity).
    """
    body = await request.json()
    # T-08-01: validate field against whitelist BEFORE touching DB or acquiring lock
    from trezarr.bible.store import MERGEABLE_FIELDS  # noqa: PLC0415

    field = body.get("field")
    if field not in MERGEABLE_FIELDS.get("term_dictionary", frozenset()):
        raise HTTPException(
            status_code=422, detail=f"Field '{field}' is not editable for term_dictionary."
        )

    session_factory = _get_session_factory(request)
    if session_factory is None:
        raise HTTPException(status_code=503, detail="No DB session available")

    from trezarr.web.worker import get_series_lock  # noqa: PLC0415
    from trezarr.bible.store import apply_human_edit_term  # noqa: PLC0415

    async with get_series_lock(series_id):  # D-81: outermost CM
        try:
            # CR-02: term_id (URL path) is authoritative — look up by PK, not body source_term
            dto, _evt = await apply_human_edit_term(
                session_factory,
                series_id=series_id,
                term_id=term_id,
                field=field,
                new_value=body.get("value"),
                lock=body.get("lock", False),
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
    return JSONResponse(dto.model_dump(by_alias=True))


# ── POST /api/series/{id}/terms ───────────────────────────────────────────────────


@router.post("/series/{series_id}/terms")
async def add_term(series_id: int, request: Request) -> JSONResponse:
    """Add a term to the series Bible via upsert_term."""
    session_factory = _get_session_factory(request)
    if session_factory is None:
        raise HTTPException(status_code=503, detail="No DB session available")

    body = await request.json()
    from trezarr.bible.store import upsert_term  # noqa: PLC0415

    dto, _events = await upsert_term(
        session_factory,
        series_id=series_id,
        source_term=body["source_term"],
        vietnamese_rendering=body.get("vietnamese_rendering", ""),
        category=body.get("category"),
        episode_key=body.get("episode_key"),
        source=body.get("source", "import"),
    )
    return JSONResponse(dto.model_dump(by_alias=True))


# ── DELETE /api/series/{id}/terms/{tid} ───────────────────────────────────────────


@router.delete("/series/{series_id}/terms/{term_id}")
async def delete_term_route(
    series_id: int, term_id: int, request: Request
) -> JSONResponse:
    """D-83: Delete a TermDictionary leaf row via store function (D-39: no inline SQLAlchemy)."""
    session_factory = _get_session_factory(request)
    if session_factory is None:
        raise HTTPException(status_code=404, detail="Term not found")

    from trezarr.bible.store import delete_term  # noqa: PLC0415

    try:
        result = await delete_term(
            session_factory,
            term_id=term_id,
            series_id=series_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return JSONResponse(result)


# ── PATCH /api/series/{id}/register ───────────────────────────────────────────────


@router.patch("/series/{series_id}/register")
async def patch_series_register(series_id: int, request: Request) -> JSONResponse:
    """D-80: Edit and optionally lock the register field for a series.

    field is hardcoded to "register" (the ORM attribute name; DTO serializes as
    "register" via CR-02 alias). Series lock (D-81) is the outermost CM.
    """
    body = await request.json()
    session_factory = _get_session_factory(request)
    if session_factory is None:
        raise HTTPException(status_code=503, detail="No DB session available")

    from trezarr.web.worker import get_series_lock  # noqa: PLC0415
    from trezarr.bible.store import apply_human_edit_series  # noqa: PLC0415

    async with get_series_lock(series_id):  # D-81: outermost CM
        try:
            dto, _evt = await apply_human_edit_series(
                session_factory,
                series_id=series_id,
                field="register",  # ORM attribute name (MERGEABLE_FIELDS["series"] = frozenset({"register"}))
                new_value=body.get("value"),
                lock=body.get("lock", False),
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
    return JSONResponse(dto.model_dump(by_alias=True))


# ── GET /api/series/{id}/bible/{entity_type}/{entity_id}/history ─────────────────


@router.get("/series/{series_id}/bible/{entity_type}/{entity_id}/history")
async def get_field_history(
    series_id: int,
    entity_type: str,
    entity_id: int,
    request: Request,
    field: str | None = None,
) -> JSONResponse:
    """D-82 / T-08-04: Return BibleEventDTOs for an entity field (LIMIT 100).

    entity_type must be in VALID_ENTITY_TYPES allowlist (T-08-04 injection guard).
    Returns empty list when DB is not configured.
    """
    if entity_type not in VALID_ENTITY_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid entity_type '{entity_type}'. Must be one of: {sorted(VALID_ENTITY_TYPES)}",
        )

    session_factory = _get_session_factory(request)
    if session_factory is None:
        return JSONResponse([])

    from trezarr.bible.store import load_field_history  # noqa: PLC0415

    dtos = await load_field_history(
        session_factory, series_id, entity_type, entity_id, field
    )
    return JSONResponse([d.model_dump(by_alias=True) for d in dtos])


# ── GET /api/pronouns ─────────────────────────────────────────────────────────────


@router.get("/pronouns")
async def get_pronouns() -> JSONResponse:
    """D-86: Return KNOWN_PRONOUN_TERMS + KINSHIP_RECIPROCAL constants from reconcile.py.

    No DB session needed — pure Python constants (single source of truth).
    """
    from trezarr.translate.reconcile import (  # noqa: PLC0415
        KNOWN_PRONOUN_TERMS_SELF,
        KNOWN_PRONOUN_TERMS_ADDRESS,
        KINSHIP_RECIPROCAL,
    )

    return JSONResponse(
        {
            "self_terms": KNOWN_PRONOUN_TERMS_SELF,
            "address_terms": KNOWN_PRONOUN_TERMS_ADDRESS,
            # Serialize tuple keys as "self_term|address_term" strings for JSON
            "kinship_reciprocal": {
                f"{k[0]}|{k[1]}": {"self_term": v[0], "address_term": v[1]}
                for k, v in KINSHIP_RECIPROCAL.items()
            },
        }
    )
