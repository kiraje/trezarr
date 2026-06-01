"""Pure-Python merge policy with lock precedence: human-lock > prior > inference (D-34).

Phase 4 never sets locked_fields in production — only tests demonstrating that
locks survive contradicting inference. Phase 8's UI is the production setter.
The get_locked_fields() accessor exists so Phase 8 can swap to a parallel
bible_lock table without touching call sites (CONTEXT.md §D-34).

IMPORTANT: compute_field_changes() operates on whatever entity snapshot is
passed to it. In store.py, _merge_inferred_in_session() passes the SQLA row
itself (not the caller's DTO), so getattr resolves against the row's current
in-session attribute values. WR-01 clarification: within the same AsyncSession,
SQLAlchemy's identity map means session.get(model, pk) returns the SAME Python
object as the caller's prior load — so the defence is not "re-read bypasses
cache", it is "read the row, never the caller's DTO." The caller's DTO may
carry pre-write state from a prior session; the SQLA row's attribute values
reflect what this transaction has materialised.

Design decisions honoured:
  D-34  human lock > prior value > new inference. get_locked_fields() is the
        single accessor point so Phase 8 can swap the backing store (JSON column
        → bible_lock table) without changing any call site.
  D-32  Skipping no-op fields (inferred == current) prevents spurious bible_event
        rows that would pollute the audit trail (BIBLE-06 carry-forward invariant).
"""
from __future__ import annotations

from typing import Any


def get_locked_fields(entity_dto: Any) -> frozenset[str]:
    """Read locked_fields off any DTO/object that carries the convention.

    Defensive — returns frozenset() if the attribute is missing. Phase 8 may
    swap entity_dto.locked_fields for a database-side lookup; the only
    contract this function exposes is "give me the set of locked field names
    for this entity."

    Args:
        entity_dto: Any object that may carry a `locked_fields` attribute
                    (a list or iterable of field-name strings). Objects lacking
                    the attribute are treated as having no locked fields.

    Returns:
        frozenset of locked field name strings. Never raises.
    """
    return frozenset(getattr(entity_dto, "locked_fields", []) or [])


def compute_field_changes(
    entity_dto: Any,
    inferred: dict[str, Any],
    locked: frozenset[str],
) -> list[tuple[str, Any, Any]]:
    """Return [(field, old, new), ...] for fields that should actually change.

    Skips fields in `locked` (human lock wins — D-34 / success criterion 4).
    Skips no-op fields where inferred == current (D-32 / BIBLE-06 carry-forward).
    Treats a missing attribute on entity_dto as old_value=None.
    Accepts new_value=None (clearing a field) as a genuine change.

    Pure function — no DB, no side effects. Easy to unit test exhaustively.

    IMPORTANT: In store.py, always call this with the SQLA row inside the
    open transaction — not the caller's external DTO. The SQLA row's
    attribute values reflect this session's in-flight view; the caller's
    DTO may carry pre-write state from a prior session. WR-01: within the
    same AsyncSession the identity map returns the same handle the caller
    holds, so this is not about cache-bypass — it is about routing the
    lookup through the SQLA model rather than the Pydantic DTO. This
    function itself has no such constraint, but the call site must enforce it.

    Args:
        entity_dto: Current-state entity object. Fields are read via getattr;
                    absent attributes are treated as old_value=None.
        inferred:   Dict mapping field names to newly-inferred values.
        locked:     frozenset of field names that are locked (see get_locked_fields).

    Returns:
        List of (field_name, old_value, new_value) tuples for fields that
        actually need to change. Empty list if all changes are locked or no-ops.
    """
    changes: list[tuple[str, Any, Any]] = []
    for field, new_val in inferred.items():
        if field in locked:
            continue
        old_val = getattr(entity_dto, field, None)
        if old_val == new_val:
            continue
        changes.append((field, old_val, new_val))
    return changes
