"""End-to-end translation engine: numbered-line protocol, batch dispatch, gate, quarantine (D-12..D-20).

Design decisions honoured:
  D-12  Inline-tag sentinel protection — extract before LLM, reinsert after.
  D-13  Numbered-line protocol guarantees 1:1 cue mapping by construction.
  D-14  Batch dispatch via asyncio.gather over LLMClient.call().
  D-15  Context window (K source lines before/after) included in every prompt.
  D-16  Document-level gate via validate_subdoc() before any write.
  D-17  Untranslated-line detection inside validate_subdoc().
  D-18  Bounded per-batch retry via tenacity on BatchValidationError ONLY.
        openai.APIError is NOT caught by tenacity (SDK handles transport failures).
  D-19  Atomic UTF-8 sidecar write via write_vi_sidecar().
  D-20  Idempotency: ledger.check() at entry; ledger.record() after write/quarantine.

Critical constraints:
  - No asyncio.Semaphore in this module.  LLMClient._semaphore is the sole gate (Pitfall 1).
  - tenacity retry wraps ONLY _translate_batch, not translate_file.
  - retry_if_exception_type(BatchValidationError) — never includes openai.APIError (Pitfall 5).
  - New SubLine objects for translated doc — never mutate source SubLines (Pitfall 8).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from trezarr.llm.client import LLMClient
from trezarr.output.ledger import Ledger, LedgerEntry
from trezarr.output.write import write_vi_sidecar
from trezarr.subtitles.model import SubDoc, SubLine
from trezarr.subtitles.srt import read_srt
from trezarr.translate.batching import Batch, batch_subdoc
from trezarr.translate.sentinel import extract_sentinels, reinsert_sentinels
from trezarr.translate.validate import GateError, validate_subdoc

if TYPE_CHECKING:
    from trezarr.config import TrezarrSettings

logger = logging.getLogger(__name__)


# ── Exception hierarchy ────────────────────────────────────────────────────────

class BatchValidationError(Exception):
    """Raised when a translated batch fails batch-level gate checks.

    Caught ONLY by the tenacity @retry decorator in _translate_batch.
    Triggers a retry of the batch (up to translate_batch_retry_attempts times).
    """


class TranslationError(Exception):
    """Raised for whole-file translation failures that trigger quarantine.

    Propagates out of _translate_batch when all tenacity retries are exhausted,
    and from translate_file when the document-level gate fails.
    """


# ── Result dataclass ───────────────────────────────────────────────────────────

@dataclass
class TranslationResult:
    """Result returned by translate_file().

    Attributes:
        status:          "done" | "skipped" | "quarantined"
        output_path:     Path to the written .vi.srt sidecar (status="done" only).
        quarantine_path: Path to the quarantine JSON artifact (status="quarantined" only).
        reason:          Human-readable description of the failure (status="quarantined" only).
    """
    status: str  # "done" | "skipped" | "quarantined"
    output_path: Path | None = None
    quarantine_path: Path | None = None
    reason: str | None = None


# ── Prompt construction ────────────────────────────────────────────────────────

def build_translate_prompt(
    batch_texts: list[str],
    context_before: list[str],
    context_after: list[str],
    source_lang: str = "English",
) -> str:
    """Build the numbered-line translation prompt (D-13, D-15, ENG-03).

    Structure:
      - Optional [CONTEXT] block before the lines to translate (context_before)
      - [LINES TO TRANSLATE] block with [1] ... [N] numbered lines
      - Optional [CONTEXT] block after the lines to translate (context_after)

    Args:
        batch_texts:     Source texts for the cues to translate, in order.
        context_before:  Read-only context lines preceding this batch.
        context_after:   Read-only context lines following this batch.
        source_lang:     Human-readable source language name (default "English").

    Returns:
        A prompt string ready to send to LLMClient.call() as a user message.
    """
    parts = [
        f"Translate the following {source_lang} subtitle lines to Vietnamese.",
        "RULES:",
        "1. Output ONLY the numbered lines [1], [2], ... [N] in order.",
        "2. Keep <<T0>>, <<T1>>, ... tokens EXACTLY as-is (formatting placeholders — never translate or modify them).",
        "3. Do NOT translate or output the [context] lines.",
        "",
    ]

    if context_before:
        parts.append("[CONTEXT - read only, do not output]")
        for line in context_before:
            parts.append(f"[context] {line.strip()}")
        parts.append("")

    parts.append("[LINES TO TRANSLATE]")
    for i, text in enumerate(batch_texts, 1):
        parts.append(f"[{i}] {text.strip()}")

    if context_after:
        parts.append("")
        parts.append("[CONTEXT - read only, do not output]")
        for line in context_after:
            parts.append(f"[context] {line.strip()}")

    return "\n".join(parts)


# ── Numbered-line response parser ──────────────────────────────────────────────

# Forgiving regex per A7 in RESEARCH.md: handles "[1] text", "[1]. text", "[1]) text"
import re as _re
_NUMBERED_LINE_RE = _re.compile(r'\[(\d+)\][.\)]?\s*(.*)')


def parse_numbered_response(response: str, expected_count: int) -> list[str]:
    """Parse a numbered-line LLM response into a list of translated strings (D-13).

    Uses a forgiving regex that handles "[N] text", "[N]. text", and "[N]) text"
    variants (Assumption A7 from RESEARCH.md).

    Args:
        response:       Raw string response from the LLM.
        expected_count: The number of lines that should be in the response.

    Returns:
        Ordered list of translated text strings (one per numbered line).

    Raises:
        BatchValidationError: If any expected line number is missing, any line is
                              empty/whitespace-only, or the parsed count != expected_count.
    """
    parsed: dict[int, str] = {}
    for raw_line in response.splitlines():
        m = _NUMBERED_LINE_RE.match(raw_line.strip())
        if m:
            line_num = int(m.group(1))
            text = m.group(2).strip()
            parsed[line_num] = text

    # Validate all expected line numbers are present
    for n in range(1, expected_count + 1):
        if n not in parsed:
            raise BatchValidationError(
                f"Missing line [{n}] in LLM response (expected {expected_count} lines)"
            )
        if not parsed[n]:
            raise BatchValidationError(
                f"Empty/whitespace-only text for line [{n}] in LLM response"
            )

    if len(parsed) < expected_count:
        raise BatchValidationError(
            f"Parsed {len(parsed)} lines but expected {expected_count}"
        )

    return [parsed[n] for n in range(1, expected_count + 1)]


# ── Batch translation with tenacity retry ─────────────────────────────────────

def _make_translate_batch_fn(settings: "TrezarrSettings"):
    """Build a tenacity-decorated _translate_batch function bound to settings.

    The retry parameters depend on settings.translate_batch_retry_attempts, which
    is only known at runtime.  We construct the decorated function once per
    translate_file() call so the stop_after_attempt value is correct.
    """
    attempts = settings.translate_batch_retry_attempts + 1  # attempts = retries + 1 initial

    @retry(
        retry=retry_if_exception_type(BatchValidationError),
        stop=stop_after_attempt(attempts),
        wait=wait_exponential(multiplier=0.5, max=4),
        reraise=True,
    )
    async def _translate_batch_inner(
        batch: Batch,
        llm_client: LLMClient,
        _settings: "TrezarrSettings",
    ) -> list[str]:
        """Translate a single batch, retrying on BatchValidationError only (D-18).

        Steps per attempt:
          1. Extract sentinels from each cue's text (D-12)
          2. Build numbered-line prompt with context (D-13, D-15)
          3. Call LLMClient.call() — NEVER bypassed, NEVER wrapped in a second Semaphore
          4. Parse the numbered-line response
          5. Reinsert sentinels; raise BatchValidationError if integrity fails

        openai.APIError is intentionally NOT caught by tenacity — the SDK handles
        transport-level retries (D-07, Pitfall 5).

        Args:
            batch:      The Batch to translate.
            llm_client: The LLM client to call.
            _settings:  Settings (passed through for future use; not used in body).

        Returns:
            List of translated text strings (one per cue in batch.cues).

        Raises:
            BatchValidationError: On count/empty/sentinel gate failure (triggers retry).
        """
        # Step 1: Extract sentinels from each cue
        cleaned_texts: list[str] = []
        sentinel_maps: list[dict[str, str]] = []
        for cue in batch.cues:
            cleaned, smap = extract_sentinels(cue.text)
            cleaned_texts.append(cleaned)
            sentinel_maps.append(smap)

        # Step 2: Build the numbered-line prompt
        context_before_texts = [c.text for c in batch.context_before]
        context_after_texts = [c.text for c in batch.context_after]
        prompt = build_translate_prompt(cleaned_texts, context_before_texts, context_after_texts)

        # Step 3: Call LLMClient (the sole concurrency gate is inside LLMClient._semaphore)
        raw_response = await llm_client.call([{"role": "user", "content": prompt}])

        # Step 4: Parse the numbered-line response
        translated_texts = parse_numbered_response(str(raw_response), len(batch.cues))

        # Step 5: Reinsert sentinels
        restored: list[str] = []
        for i, (text, smap) in enumerate(zip(translated_texts, sentinel_maps)):
            if smap:
                restored_text, integrity_ok = reinsert_sentinels(text, smap)
                if not integrity_ok:
                    raise BatchValidationError(
                        f"Sentinel integrity failure for cue {i}: "
                        f"sentinel(s) not found or orphan tokens remain in {restored_text!r}"
                    )
                restored.append(restored_text)
            else:
                restored.append(text)

        return restored

    return _translate_batch_inner


async def _translate_batch(
    batch: Batch,
    llm_client: LLMClient,
    settings: "TrezarrSettings",
) -> list[str]:
    """Public entry point for translating a single batch with retry.

    Thin wrapper that builds a settings-bound tenacity-decorated function and
    calls it.  Exposed as a module-level name for testing (test_engine.py).

    Args:
        batch:      The Batch to translate.
        llm_client: The LLM client to call.
        settings:   Settings supplying translate_batch_retry_attempts.

    Returns:
        List of translated text strings.

    Raises:
        BatchValidationError: If all retries are exhausted (reraise=True in decorator).
    """
    fn = _make_translate_batch_fn(settings)
    return await fn(batch, llm_client, settings)


# ── Quarantine artifact write ──────────────────────────────────────────────────

def _write_quarantine(
    source_path: Path,
    reason: str,
    failing_indices: list[int],
    settings: "TrezarrSettings",
) -> Path:
    """Write a quarantine JSON artifact for a failed translation (D-18, T-02-03-03).

    The artifact contains only: reason, failing_cue_indices, timestamp, source_path.
    It intentionally does NOT include cue text — source subtitles may be proprietary
    (T-02-03-03: information disclosure control).

    Args:
        source_path:     Absolute path to the source SRT file.
        reason:          Human-readable failure description.
        failing_indices: List of cue indices that triggered the failure.
        settings:        Settings supplying translate_quarantine_dir.

    Returns:
        Path to the written quarantine JSON file.
    """
    quarantine_dir = Path(settings.translate_quarantine_dir)
    quarantine_dir.mkdir(parents=True, exist_ok=True)

    artifact_name = source_path.stem + ".json"
    quarantine_path = quarantine_dir / artifact_name

    artifact = {
        "reason": reason,
        "failing_cue_indices": failing_indices,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "source_path": str(source_path),
        # NOTE: cue text is explicitly excluded — T-02-03-03 (proprietary content)
    }

    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w',
            encoding='utf-8',
            suffix='.tmp',
            dir=quarantine_dir,
            delete=False,
        ) as f:
            tmp_path = Path(f.name)
            json.dump(artifact, f, indent=2)
        os.replace(tmp_path, quarantine_path)
        tmp_path = None
    finally:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink()

    return quarantine_path


# ── Main entry point ───────────────────────────────────────────────────────────

async def translate_file(
    path: str | Path,
    settings: "TrezarrSettings",
    llm_client: LLMClient,
    ledger: Ledger,
) -> TranslationResult:
    """Translate a source SRT file to Vietnamese and write a .vi.srt sidecar.

    This is the Phase-3-callable entry point for the translation pipeline.

    Steps:
      1. Resolve path to absolute; read source bytes; compute content hash
      2. Derive destination .vi.srt path
      3. Ledger check (D-20 behavior table):
         - done + dest.exists() + hash matches → skip (idempotent no-op)
         - dest.exists() + not in ledger → foreign file, skip + log
         - quarantined → proceed (retry)
         - in_progress → proceed (previous run crashed)
         - not in ledger → proceed
      4. Record in_progress in ledger
      5. read_srt() → source SubDoc
      6. batch_subdoc() → list[Batch]
      7. asyncio.gather() dispatches all batches concurrently
      8. Assemble translated SubDoc (new SubLine objects — never mutate source)
      9. validate_subdoc() document-level gate
      10. write_vi_sidecar() atomic UTF-8 write
      11. ledger.record(status="done")
      12. Return TranslationResult(status="done")

    On any failure (retry exhaustion or gate failure):
      - Write quarantine artifact (no cue text — T-02-03-03)
      - ledger.record(status="quarantined")
      - Return TranslationResult(status="quarantined")

    Args:
        path:       Path to the source SRT file (str or Path; resolved to absolute).
        settings:   TrezarrSettings supplying all pipeline configuration.
        llm_client: LLMClient instance (Phase-1, semaphore-gated).
        ledger:     Ledger instance for idempotency tracking.

    Returns:
        TranslationResult with status "done", "skipped", or "quarantined".
    """
    # Step 1: Resolve path and compute content hash
    path = Path(path).resolve()
    source_bytes = path.read_bytes()
    content_hash = Ledger.content_hash(source_bytes)

    # Step 2: Derive destination path (same logic as write_vi_sidecar)
    import re as _re2
    _lang_re = _re2.compile(r'\.[a-z]{2}$', _re2.IGNORECASE)
    stem = path.stem
    if _lang_re.search(stem):
        stem = stem.rsplit('.', 1)[0]
    dest = path.parent / (stem + '.vi.srt')

    # Step 3: Ledger check (D-20 behavior table)
    entry = ledger.check(str(path))

    # Foreign file: dest exists but source_path not in ledger → skip + log (T-02-03-04)
    if entry is None and dest.exists():
        logger.info("foreign vi.srt at %s, not ours — skipping %s", dest, path)
        return TranslationResult(status="skipped")

    # Already done + dest exists + hash matches → idempotent skip
    if (
        entry is not None
        and entry.status == "done"
        and dest.exists()
        and entry.content_hash == content_hash
    ):
        return TranslationResult(status="skipped")

    # Step 4: Record in_progress (in case this run crashes mid-flight)
    ledger.record(LedgerEntry(
        source_path=str(path),
        output_path=str(dest),
        status="in_progress",
        content_hash=content_hash,
    ))

    # Steps 5-6: Read and batch the source.  Both can raise on poisoned source files
    # (PermissionError, decode errors, malformed SRT).  A raise here would leave the
    # ledger at in_progress forever — catch and quarantine per the function contract.
    try:
        source_doc = read_srt(path)
        batches = batch_subdoc(source_doc, settings)
    except Exception as exc:
        reason = f"read/batch failure: {exc}"
        quarantine_path = _write_quarantine(path, reason, [], settings)
        ledger.record(LedgerEntry(
            source_path=str(path),
            output_path=None,
            status="quarantined",
            content_hash=content_hash,
            quarantine_path=str(quarantine_path),
        ))
        return TranslationResult(
            status="quarantined",
            quarantine_path=quarantine_path,
            reason=reason,
        )

    # Step 7: Dispatch all batches concurrently via asyncio.gather
    # ONLY catch BatchValidationError (retry-exhausted batch gate failure → quarantine).
    # openai.APIError and any other exception propagate: the file stays out of "done"
    # and is retried on the next poll cycle.  Pitfall 5 / D-18: SDK handles transport
    # failures; never permanently quarantine on a transient endpoint error.
    try:
        batch_results = await asyncio.gather(
            *[_translate_batch(b, llm_client, settings) for b in batches]
        )
    except BatchValidationError as exc:
        reason = str(exc)
        quarantine_path = _write_quarantine(path, reason, [], settings)
        ledger.record(LedgerEntry(
            source_path=str(path),
            output_path=None,
            status="quarantined",
            content_hash=content_hash,
            quarantine_path=str(quarantine_path),
        ))
        return TranslationResult(
            status="quarantined",
            quarantine_path=quarantine_path,
            reason=reason,
        )

    # Step 8: Assemble translated SubDoc (Pitfall 8 — never mutate source SubLines)
    translated_lines: list[SubLine] = []
    cue_idx = 0
    for batch, translated_texts in zip(batches, batch_results):
        for src_line, translated_text in zip(batch.cues, translated_texts):
            translated_lines.append(SubLine(
                index=src_line.index,
                start_tc=src_line.start_tc,
                end_tc=src_line.end_tc,
                text=translated_text,
                raw=None,  # well-formed translated cue — raw not needed
            ))
            cue_idx += 1

    translated_doc = SubDoc(
        lines=translated_lines,
        encoding='utf-8',
        line_ending=source_doc.line_ending,
        separators=source_doc.separators,
        leading=source_doc.leading,
        trailer=source_doc.trailer,
    )

    # Step 9: Document-level validation gate (D-16, D-17)
    try:
        validate_subdoc(translated_doc, source_doc, settings)
    except GateError as exc:
        reason = str(exc)
        failing_indices = exc.failure.failing_indices or []
        quarantine_path = _write_quarantine(path, reason, failing_indices, settings)
        ledger.record(LedgerEntry(
            source_path=str(path),
            output_path=None,
            status="quarantined",
            content_hash=content_hash,
            quarantine_path=str(quarantine_path),
        ))
        return TranslationResult(
            status="quarantined",
            quarantine_path=quarantine_path,
            reason=reason,
        )

    # Step 10: Atomic UTF-8 write (D-19)
    output_path = write_vi_sidecar(translated_doc, path)

    # Step 11: Record completion in ledger
    ledger.record(LedgerEntry(
        source_path=str(path),
        output_path=str(output_path),
        status="done",
        content_hash=content_hash,
        translated_at=datetime.utcnow().isoformat() + "Z",
    ))

    # Step 12: Return success result
    return TranslationResult(status="done", output_path=output_path)
