"""Gap detection: decides whether an item needs translation (D-26, D-27, D-28).

Design decisions honoured:
  D-26  Gap = source sub present AND no honored vi sidecar; foreign vi → skip+log,
        never clobber. Bazarr-collision safety (Pitfall 10).
  D-27  content_hash IS the source-subtitle hash (SHA-256[:16] of source bytes).
        No new field — the existing LedgerEntry.content_hash IS the comparison
        key (per 03-RESEARCH.md Pitfall 7). Two parallel hashes would create
        divergence risk between translate_file()'s skip logic and gap-detection's
        re-translate check.
  D-28  Self-output exclusion via ledger provenance — our output is in the ledger,
        a foreign vi sidecar is not. In Phase 3 there is no watcher yet, so the
        ledger provenance IS the exclusion mechanism.

Per 03-REVIEWS.md HIGH #4: ``is_eligible`` takes ``(source_sub_path, ledger)`` —
the originally-listed video-path parameter is dropped because the
adjacency-to-the-media-file invariant is structurally enforced by the caller
(``scan.scan_for_eligible_items`` discovers ``source_sub_path`` via a glob
inside the video file's parent directory, so the source sub IS adjacent to
the video file by construction). No additional adjacency check is needed
inside is_eligible.

Per 03-RESEARCH.md Pitfall 5: the vi sidecar path is ALWAYS derived from the
``source_sub_path``, never from the video path. ``derive_vi_sidecar_path`` in
``trezarr.output.write`` knows how to strip the source-language suffix and
append ``.vi<ext>`` mirroring the source extension; passing it the video path
would yield a wrong target.
"""
from __future__ import annotations

import logging
from pathlib import Path

from trezarr.output._ledger_protocol import LedgerProtocol
from trezarr.output.ledger import Ledger
from trezarr.output.write import derive_vi_sidecar_path

logger = logging.getLogger(__name__)


async def is_eligible(source_sub_path: Path, ledger: LedgerProtocol) -> tuple[bool, str]:
    """Decide whether a source-subtitle file is eligible for (re-)translation.

    Per 03-REVIEWS.md HIGH #4: signature is ``(source_sub_path, ledger)`` —
    the video-path parameter is intentionally absent. The original spec passed
    a video path so the function could re-derive the vi sidecar from the video
    file, but ``derive_vi_sidecar_path`` actually takes the source-sub path
    (it strips the ".en" / ".ja" / etc. lang suffix and appends ".vi<ext>"
    mirroring the source extension). Passing the video path would be wrong
    (Pitfall 5).

    Decision matrix (in evaluation order):

      Case 0  source_sub_path does not exist on disk
              ⇒ (False, "no source subtitle at <path>")

      Case 1  vi_path exists AND no ledger entry for source_sub_path
              ⇒ (False, "foreign vi sidecar at <vi_path> — not ours, skipping")
              D-26 never-clobber-foreign-vi guard. Bazarr or some other tool
              wrote this; we leave it alone.

      Case 2  ledger entry exists, status=done, AND vi_path exists
              ⇒ compare current source-bytes hash against entry.content_hash
                ⇒ unchanged  → (False, "already translated (source unchanged)")
                ⇒ changed    → (True,  "source subtitle changed — re-translating")
              D-27 idempotency on source-sub hash.

      Case 3  ledger entry status=quarantined
              ⇒ (True, "retrying previously quarantined item")
              D-30 quarantine retry on re-run.

      Case 4  ledger entry status=in_progress
              ⇒ (True, "resuming in-progress item (possibly crashed run)")
              Defensive recovery — a crash mid-translate would leave
              status=in_progress; the next run picks it up.

      Default ⇒ (True, "new item")
              No vi sidecar present AND no ledger entry — straightforward case.

    D-28 self-output exclusion: when ``translate_file()`` writes a vi sidecar,
    it records a LedgerEntry. Next run: vi_path exists AND entry is not None
    ⇒ Case 2 (skip if unchanged). The ledger provenance IS the self-exclusion
    mechanism in Phase 3 (no watcher yet to emit events that would otherwise
    need an event-time guard).

    Args:
        source_sub_path: Absolute path to the source subtitle file. ``Pitfall
                         5``: do NOT pass the video path here.
        ledger:          The Ledger instance carrying processed-file provenance.

    Returns:
        ``(eligible: bool, reason: str)`` — ``reason`` is human-readable and
        used for log output; scan.py classifies the False reasons via simple
        substring match ("foreign", "already translated") to bump the right
        ScanStats counter.
    """
    # Case 0 — defensive: a missing source file is not eligible. The
    # scan_for_eligible_items() caller pre-filters via find_source_sub None,
    # but downstream callers (CLI, future watcher) may invoke is_eligible
    # directly on arbitrary paths.
    if not source_sub_path.exists():
        return (False, f"no source subtitle at {source_sub_path}")

    vi_path = derive_vi_sidecar_path(source_sub_path)  # Pitfall 5 — source_sub_path, not video
    entry = await ledger.check(str(source_sub_path))

    # Case 1 — foreign vi sidecar (D-26): vi present, ledger has no record.
    # We did NOT write this; never clobber (D-26, D-96: applies to .vi.<ext> for all formats).
    if vi_path.exists() and entry is None:
        logger.info(
            "foreign vi sidecar at %s — skipping %s (D-26, never clobber)",
            vi_path, source_sub_path,
        )
        return (False, f"foreign vi sidecar at {vi_path} — not ours, skipping")

    if entry is not None:
        # Case 2 — done + vi present: source-hash idempotency check (D-27).
        if entry.status == "done" and vi_path.exists():
            try:
                current_hash = Ledger.content_hash(source_sub_path.read_bytes())
            except OSError as exc:
                # Source unreadable — treat as no-source.
                return (False, f"source subtitle unreadable: {exc}")
            if entry.content_hash == current_hash:
                return (False, "already translated (source unchanged)")
            return (True, "source subtitle changed — re-translating")

        # Case 3 — quarantined: retry on every run (D-30 batch semantics).
        if entry.status == "quarantined":
            return (True, "retrying previously quarantined item")

        # Case 4 — in_progress: crashed-run recovery. The ledger record was
        # created at translate-start but never updated to done/quarantined —
        # we pick it up again.
        if entry.status == "in_progress":
            return (True, "resuming in-progress item (possibly crashed run)")

    # Case 5 (default) — no ledger entry, no foreign vi: brand-new item.
    return (True, "new item")
