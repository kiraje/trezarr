"""Pure-Python unit tests for trezarr.bible.merge policy functions.

Tests are fully synchronous (no async, no fixtures beyond types.SimpleNamespace).
All eight tests exercise lock-precedence + no-op detection without any DB.

Design decisions exercised:
  D-34  human lock > prior value > new inference
  D-32  no-op fields emit zero events (BIBLE-06 carry-forward)
  BIBLE-06  same inference across episodes leaves the entity unchanged
"""
from __future__ import annotations

from types import SimpleNamespace

from trezarr.bible.merge import compute_field_changes, get_locked_fields


# ---------------------------------------------------------------------------
# Test 1: get_locked_fields returns frozenset from a DTO with locked_fields
# ---------------------------------------------------------------------------

def test_get_locked_fields_returns_frozenset_from_dto():
    """An entity DTO with locked_fields=["role", "name"] returns frozenset({"role","name"})."""
    dto = SimpleNamespace(locked_fields=["role", "name"])
    result = get_locked_fields(dto)
    assert result == frozenset({"role", "name"})
    assert isinstance(result, frozenset)


# ---------------------------------------------------------------------------
# Test 2: get_locked_fields is defensive on missing attribute
# ---------------------------------------------------------------------------

def test_get_locked_fields_returns_empty_on_missing_attribute():
    """An object without a locked_fields attribute returns frozenset() — no AttributeError."""
    obj = SimpleNamespace(role="detective")  # no locked_fields attribute
    result = get_locked_fields(obj)
    assert result == frozenset()
    assert isinstance(result, frozenset)


# ---------------------------------------------------------------------------
# Test 3: compute_field_changes skips locked fields
# ---------------------------------------------------------------------------

def test_compute_field_changes_skips_locked_fields():
    """Locked field wins over inferred value — no change entry emitted (D-34)."""
    entity = SimpleNamespace(role="detective", locked_fields=["role"])
    locked = get_locked_fields(entity)
    result = compute_field_changes(entity, {"role": "spy"}, locked)
    assert result == [], "locked field must produce no change"


# ---------------------------------------------------------------------------
# Test 4: compute_field_changes skips no-op inferences
# ---------------------------------------------------------------------------

def test_compute_field_changes_skips_no_op_inferences():
    """No-op inference (inferred == current) produces empty list (BIBLE-06 carry-forward)."""
    entity = SimpleNamespace(role="detective", locked_fields=[])
    locked = get_locked_fields(entity)
    result = compute_field_changes(entity, {"role": "detective"}, locked)
    assert result == [], "no-op inference must produce no change"


# ---------------------------------------------------------------------------
# Test 5: compute_field_changes emits change for genuine update
# ---------------------------------------------------------------------------

def test_compute_field_changes_emits_change_for_genuine_update():
    """Unlocked field with different inferred value produces (field, old, new) tuple."""
    entity = SimpleNamespace(role="detective", locked_fields=[])
    locked = get_locked_fields(entity)
    result = compute_field_changes(entity, {"role": "spy"}, locked)
    assert result == [("role", "detective", "spy")]


# ---------------------------------------------------------------------------
# Test 6: compute_field_changes handles multiple fields with partial locks
# ---------------------------------------------------------------------------

def test_compute_field_changes_handles_multiple_fields_partial_locks():
    """role locked, gender unlocked+changed — only gender appears in changes."""
    entity = SimpleNamespace(role="detective", gender="female", locked_fields=["role"])
    locked = get_locked_fields(entity)
    result = compute_field_changes(entity, {"role": "spy", "gender": "other"}, locked)
    assert result == [("gender", "female", "other")], (
        "locked field (role) must be skipped; unlocked changed field (gender) must appear"
    )


# ---------------------------------------------------------------------------
# Test 7: compute_field_changes treats absent attribute as old_value=None
# ---------------------------------------------------------------------------

def test_compute_field_changes_inferred_field_not_on_entity_is_treated_as_old_none():
    """Missing attribute on entity is treated as old_value=None — never crashes."""
    entity = SimpleNamespace(role="detective")  # no 'nickname' attribute
    locked = frozenset()
    result = compute_field_changes(entity, {"nickname": "The Spy"}, locked)
    assert result == [("nickname", None, "The Spy")]


# ---------------------------------------------------------------------------
# Test 8: compute_field_changes accepts clearing a field to None
# ---------------------------------------------------------------------------

def test_compute_field_changes_clearing_field_to_none():
    """Inferred new_value=None counts as a genuine change — produces (field, old, None)."""
    entity = SimpleNamespace(role="detective", locked_fields=[])
    locked = get_locked_fields(entity)
    result = compute_field_changes(entity, {"role": None}, locked)
    assert result == [("role", "detective", None)], (
        "clearing a field to None must produce a change entry with new_value=None"
    )
