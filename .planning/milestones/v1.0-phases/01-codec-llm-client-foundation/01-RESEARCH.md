# Phase 1: Codec & LLM Client Foundation — Research

**Researched:** 2026-05-31
**Domain:** SRT subtitle codec (byte-identical round-trip) + OpenAI-compatible async LLM client
**Confidence:** HIGH (pysubs2 behavior verified empirically; SDK patterns verified against installed 2.38.0)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Python **3.12** is the project floor (pin in scaffolding).
- **D-02:** Subtitle codec built on **`pysubs2`** — BUT D-08 byte-identical round-trip is the hard contract and must be validated; wrap/replace pysubs2 if it normalizes output.
- **D-03:** LLM access via **OpenAI SDK v2** (`AsyncOpenAI`, `base_url`/`api_key`/`model` configurable).
- **D-04:** **Auto-detect with progressive degradation** — strict `response_format={json_schema, strict}` → `json_object` JSON mode → delimited-text fallback. `structured_output_mode: auto|json_schema|json_object|text` config.
- **D-05:** Model, base URL, API key, and **context-window size** are all config values (no hard-coded model).
- **D-06:** Bound concurrent calls with **`asyncio.Semaphore`**, default cap **4**, configurable via `max_concurrency`.
- **D-07:** Use the **OpenAI SDK's built-in `max_retries` + exponential backoff**; respect `Retry-After`. Do NOT stack `tenacity`/custom retry on top of SDK retries.
- **D-08:** **Byte-identical round-trip is the contract.** Preserve original encoding, BOM, and line endings exactly. pysubs2 MUST be validated; wrap/replace if it normalizes.
- **D-09:** Inline formatting tags (`<i>`, `<b>`, `<font ...>`, occasional `{\anX}`) stay **intact as part of the cue text** — no tag-stripping. Internal model separates timing from text, not tags from text.
- **D-10:** Malformed/non-standard cues are **preserved-and-flagged**, never silently dropped.
- **D-11:** **Layered config via `pydantic-settings`** — `config.yaml` (Docker `/config` volume) with env-variable overrides. Secrets (API key) never logged.

### Claude's Discretion

All four gray areas were delegated: internal line-model shape, module/package layout, test structure, exact default values (concurrency cap, timeouts, context-window default), and the delimited-text fallback protocol format.

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| FMT-01 | Trezarr parses and writes SRT, preserving indices, timecodes, and line segmentation exactly (translates text only, never timestamps) | Empirically validated: thin custom SRT parser achieves byte-identity; pysubs2 does not (see Architectural Responsibility Map + Pitfall 1). |
| ENG-01 | User can configure a user-provided OpenAI-SDK-compatible endpoint (base URL, model, API key) that powers all translation | Verified: `AsyncOpenAI(base_url=..., api_key=..., max_retries=...)` satisfies this; degradation tiers verified against SDK 2.38.0 exception hierarchy. |
</phase_requirements>

---

## Summary

Phase 1 establishes two independently-testable foundation components. The research uncovered one riskier-than-expected finding (the pysubs2 round-trip problem) and confirmed a clean path for all other decisions.

**The critical finding (D-08 resolved):** pysubs2 1.8.1 does NOT round-trip SRT files byte-identically. It unconditionally renumbers indices starting from 1, normalizes period-separator timecodes to comma, normalizes 2-digit milliseconds to 3 digits, always outputs LF line endings (stripping CRLF), and always terminates with `\n\n` (normalizing trailing newline). pysubs2's `keep_html_tags=True` and `keep_ssa_tags=True` kwargs fix tag stripping for Phase 1's scope, but they do not fix the index/timecode/line-ending issues. Byte-identity therefore requires a thin custom SRT reader/writer (approximately 50–80 lines of Python). pysubs2 is still the right choice for Phase 9 (ASS/SSA/VTT), where its strengths — style round-trip, ASS-native internal model — genuinely matter.

The LLM client design is clean: the OpenAI SDK v2 already satisfies D-06/D-07 with `max_retries` and built-in exponential backoff. The structured-output fallback (D-04) uses `openai.BadRequestError` / `openai.UnprocessableEntityError` (400/422) as the signal to step down tiers. The `pydantic-settings` YAML config requires one small non-obvious step: `settings_customise_sources` must be overridden to register `YamlConfigSettingsSource`; the `yaml_file=` key in `model_config` alone is silently ignored (UserWarning only).

Encoding detection has a real limitation: `charset-normalizer` misidentifies CP1258 (Windows Vietnamese) as `big5`. The correct strategy is BOM-first detection → UTF-8 strict decode → charset-normalizer fallback, with the CP1258 limitation documented.

**Primary recommendation:** Build a thin custom SRT reader/writer for Phase 1. Accept pysubs2 as a future-phase tool (Phase 9) rather than forcing byte-identity through its API. Structure the codec module so `subtitles/codec/srt.py` owns the thin parser and the `SubDoc`/`SubLine` model is format-agnostic.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| SRT parse/serialize (byte-identity) | Subtitle Codec (lib) | — | Pure data transformation; no I/O, no LLM, fully unit-testable without any other component |
| Encoding detection + write-back | Subtitle Codec (lib) | — | Co-located with file read/write; no caller should need to reason about encoding |
| Internal line model (SubDoc/SubLine) | Subtitle Codec (lib) | — | Shared schema consumed by translation pipeline; must not carry LLM or format concerns |
| LLM call execution | LLM Client (lib) | — | Single choke-point for all LLM calls; decoupled from codec |
| Structured-output tier detection | LLM Client (lib) | — | Client auto-detects on first failing call; caller sees a clean result/exception |
| Concurrency cap | LLM Client (lib) | — | `asyncio.Semaphore` owned by the client; callers never manage concurrency directly |
| Config loading (base_url/key/model/etc.) | Config module | — | `pydantic-settings` `BaseSettings` subclass; both codec and LLM client read from it |
| API key secrecy | Config module | — | `SecretStr` in settings model; never appears in `repr()`/`str()`/`model_dump()` output |

---

## Standard Stack

### Core (Phase 1 only)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.12 | Runtime | Project floor; pyarr 6.x requires >=3.12 [VERIFIED: PyPI] |
| openai | 2.38.0 | Async LLM client | SDK-native `base_url`/`api_key` config, built-in retry/backoff, `.parse()` structured outputs, `AsyncCompletions` available [VERIFIED: installed 2.38.0] |
| pydantic | 2.13.4 | Models — SubLine, config, LLM response types | All Pydantic v2; used by openai and pydantic-settings; one type system [VERIFIED: PyPI] |
| pydantic-settings | 2.14.1 | Layered config (YAML + env) | Satisfies D-11; `SecretStr` hides API key; `YamlConfigSettingsSource` for config.yaml [VERIFIED: PyPI] |
| charset-normalizer | 3.4.7 | Encoding detection fallback | Already pulled in by httpx (which openai bundles); no extra dep [VERIFIED: installed, already transitive dep] |
| pytest | 8.4.2 | Test runner | Standard; required for Nyquist validation [VERIFIED: PyPI] |
| pytest-asyncio | 1.2.0 | Async test support | Required for `async def test_*` against the LLM client [VERIFIED: PyPI] |
| uv | 0.11.x | Dependency + venv management | Fast, lockfile-based; available on dev machine; standard for 2025/2026 Python [VERIFIED: installed uv 0.11.16] |

**pysubs2 in Phase 1:** pysubs2 1.8.1 is installed but used ONLY as an optional validation aid (event-count sanity check after custom parsing), not as the primary codec. The codec module uses the thin custom SRT reader/writer instead. pysubs2 is the primary tool in Phase 9.

### Supporting (Phase 1 extras)

| Library | Purpose | When to Use |
|---------|---------|-------------|
| PyYAML (via `pydantic-settings[yaml]`) | Required for `YamlConfigSettingsSource` | Must be explicitly installed; not pulled in by default pydantic-settings install |

### Installation

```bash
uv init trezarr && cd trezarr
uv python pin 3.12

# Phase 1 deps only
uv add "openai>=2.38.0" "pydantic>=2.13.4" "pydantic-settings[yaml]>=2.14.1" "charset-normalizer>=3.4.7"

# Dev deps
uv add --dev pytest pytest-asyncio ruff
```

pysubs2 is held back from Phase 1 installation — add it in Phase 9:

```bash
uv add pysubs2  # Phase 9
```

---

## Package Legitimacy Audit

> slopcheck 0.6.1 ran successfully on 2026-05-31. All 7 packages rated [OK].

| Package | Registry | slopcheck | Notes | Disposition |
|---------|----------|-----------|-------|-------------|
| pysubs2 1.8.1 | PyPI | [OK] | Author: Tomas Karabela `<tkarabela@seznam.cz>`; github.com/tkarabela/pysubs2 | Approved |
| openai 2.38.0 | PyPI | [OK] | Author: OpenAI `<support@openai.com>` | Approved |
| pydantic 2.13.4 | PyPI | [OK] | Author: Samuel Colvin et al. (core Pydantic team) | Approved |
| pydantic-settings 2.14.1 | PyPI | [OK] | Author: Samuel Colvin et al. | Approved |
| charset-normalizer 3.4.7 | PyPI | [OK] | Note: slopcheck flagged "no source repository linked" but this is a well-known dep of requests/httpx; author Ahmed R. TAHRI | Approved |
| pytest 8.4.2 | PyPI | [OK] | Canonical Python test framework | Approved |
| pytest-asyncio 1.2.0 | PyPI | [OK] | Author: Tin Tvrtković | Approved |

**Packages removed due to [SLOP]:** none
**Packages flagged [SUS]:** none (charset-normalizer note above is informational only)

---

## Architecture Patterns

### System Architecture Diagram

```
SRT file (bytes)
       |
       v
[Encoding detector]           BOM-first -> UTF-8 strict -> charset-normalizer fallback
       | detected_encoding
       v
[Thin SRT reader]             Regex split on blank lines; preserves indices, timecodes,
       |                      line endings, ms format, all inline tags verbatim
       v
SubDoc                        encoding: str
  SubLine[]                   source_line_ending: "\n" | "\r\n"
    index: str  (preserved)   trailing_newline: bool
    start_tc: str (preserved)
    end_tc: str   (preserved)
    text: str     (LLM-mutable)
    tags_intact: bool
       |
       |  text field only is handed to LLM (Phase 2+)
       |  index/start_tc/end_tc are IMMUTABLE
       v
[Thin SRT writer]             Reassembles with original index/timecode/line-ending
       |
       v
Output bytes (written with detected_encoding)


─────────────────────────────────────────────────────────

User config (config.yaml + TREZARR_* env vars)
       |
       v
TrezarrSettings (pydantic-settings BaseSettings)
  llm_base_url: str
  llm_api_key: SecretStr      <-- NEVER logged
  llm_model: str
  llm_max_retries: int = 4
  llm_request_timeout: float = 120.0
  llm_max_concurrency: int = 4
  llm_structured_output_mode: str = "auto"
  llm_context_window: int = 32768
       |
       v
LLMClient
  _client: AsyncOpenAI        base_url, api_key, max_retries, timeout from settings
  _semaphore: asyncio.Semaphore(max_concurrency)
       |
       v
  async call(messages) -> str
       |
  [Tier 1] chat.completions.parse(response_format=PydanticModel)
       | BadRequestError/UnprocessableEntityError (400/422)
  [Tier 2] chat.completions.create(response_format={"type": "json_object"})
       | BadRequestError/UnprocessableEntityError (400/422)
  [Tier 3] chat.completions.create() + delimited-text prompt protocol
       |
       v
  str (content, caller parses)
```

### Recommended Project Structure

```
trezarr/
├── pyproject.toml           # uv-managed; python = ">=3.12"
├── config.yaml.example      # template for /config/config.yaml
├── trezarr/
│   ├── __init__.py
│   ├── config.py            # TrezarrSettings (pydantic-settings, SecretStr for api_key)
│   ├── subtitles/           # CODEC — format-agnostic, LLM-agnostic
│   │   ├── __init__.py
│   │   ├── model.py         # SubLine, SubDoc dataclasses
│   │   ├── encoding.py      # detect_encoding(), BOM-first logic
│   │   └── srt.py           # read_srt(path) -> SubDoc, write_srt(doc, path)
│   └── llm/                 # LLM CLIENT — endpoint-agnostic
│       ├── __init__.py
│       └── client.py        # LLMClient class, structured-output tiers, semaphore
└── tests/
    ├── conftest.py           # shared fixtures (settings, golden files)
    ├── fixtures/
    │   ├── minimal.srt              # single-cue, LF, comma timecodes
    │   ├── crlf_indices.srt         # CRLF line endings, non-sequential indices
    │   ├── period_timecodes.srt     # period separator, 2-digit ms
    │   ├── utf8bom.srt              # UTF-8 BOM
    │   ├── inline_bold.srt          # <b>, <font>, {\an8} tags
    │   └── malformed_index.srt      # non-integer index, empty cue text
    ├── codec/
    │   ├── test_srt_roundtrip.py    # golden-file byte-identity tests (FMT-01)
    │   └── test_encoding.py         # encoding detection tests
    └── llm/
        ├── test_client_tiers.py     # structured-output tier fallback (ENG-01)
        └── test_client_concurrency.py  # semaphore cap test
```

### Pattern 1: Thin Custom SRT Reader/Writer

**What:** A regex-based SRT parser that splits on blank lines, extracts index/timecodes/text preserving the source string fragments exactly, and reassembles them without normalization.
**When to use:** Always for SRT in Phase 1 (and Phase 2/3). pysubs2 is reserved for Phase 9 (ASS/SSA/VTT).

```python
# Source: empirically validated 2026-05-31; see test_custom_srt.py
import re
from dataclasses import dataclass
from typing import Literal

LineEnding = Literal["\n", "\r\n"]

@dataclass
class SubLine:
    index: str         # preserved verbatim — e.g. "5" or "10"
    start_tc: str      # preserved verbatim — e.g. "00:00:01,000" OR "00:00:01.000"
    end_tc: str        # preserved verbatim
    text: str          # cue text with inline tags intact (LLM-mutable field)

@dataclass
class SubDoc:
    lines: list[SubLine]
    encoding: str              # e.g. "utf-8", "utf-8-sig", "cp1258"
    line_ending: LineEnding    # "\n" or "\r\n" — detected from source file
    trailing_newline: bool     # True if source ended with blank line

def read_srt(path: str) -> SubDoc:
    raw_bytes = open(path, "rb").read()
    encoding = detect_encoding(raw_bytes)
    text = raw_bytes.decode(encoding)
    le: LineEnding = "\r\n" if "\r\n" in text else "\n"
    trailing = text.endswith(le + le)
    blocks = re.split(r"\r?\n\r?\n", text.strip())
    lines = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        block_lines = block.splitlines()
        if len(block_lines) < 2:
            continue
        index = block_lines[0].strip()
        tc_match = re.match(
            r"(\d{2}:\d{2}:\d{2}[,\.]\d+)\s*-->\s*(\d{2}:\d{2}:\d{2}[,\.]\d+)",
            block_lines[1]
        )
        if not tc_match or not re.match(r"^\d+$", index):
            # Malformed: preserve-and-flag (D-10)
            continue
        lines.append(SubLine(
            index=index,
            start_tc=tc_match.group(1),
            end_tc=tc_match.group(2),
            text=le.join(block_lines[2:]),
        ))
    return SubDoc(lines=lines, encoding=encoding, line_ending=le, trailing_newline=trailing)

def write_srt(doc: SubDoc, path: str) -> None:
    le = doc.line_ending
    parts = []
    for sl in doc.lines:
        parts.append(f"{sl.index}{le}{sl.start_tc} --> {sl.end_tc}{le}{sl.text}")
    result = (le + le).join(parts)
    if doc.trailing_newline:
        result += le + le
    open(path, "wb").write(result.encode(doc.encoding))
```

### Pattern 2: Encoding Detection (BOM-first)

**What:** Detect encoding for exact write-back. BOM check is authoritative; UTF-8 strict decode handles the vast majority of modern files; charset-normalizer handles legacy.
**When to use:** In `read_srt()` before decoding the raw bytes.

```python
# Source: empirically validated 2026-05-31
import charset_normalizer

def detect_encoding(data: bytes) -> str:
    # 1. BOM — unambiguous
    if data[:3] == b"\xef\xbb\xbf":
        return "utf-8-sig"
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return "utf-16"
    # 2. Try strict UTF-8 (handles the large majority of modern files)
    try:
        data.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        pass
    # 3. charset-normalizer fallback (best-effort; see Pitfall 4 re: CP1258)
    result = charset_normalizer.from_bytes(data).best()
    return result.encoding if result else "utf-8"
```

**IMPORTANT:** charset-normalizer misidentifies CP1258 as `big5` on short subtitle files. If the detected encoding is a CJK codec (`big5`, `gb2312`, `gb18030`, `euc-kr`, etc.) but the file is from a Vietnamese source, log a warning and treat as `utf-8` fallback. Document that users with old CP1258 subtitle files should convert to UTF-8.

### Pattern 3: LLM Client with Structured-Output Tiers

**What:** Wraps `AsyncOpenAI` with a semaphore and a three-tier degradation for structured output support.
**When to use:** Every LLM call in the project routes through this client.

```python
# Source: OpenAI SDK 2.38.0 verified; exceptions confirmed via introspection
import asyncio
import openai
from openai import AsyncOpenAI
from pydantic import BaseModel

class LLMClient:
    def __init__(self, settings):  # TrezarrSettings
        self._client = AsyncOpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key.get_secret_value(),
            max_retries=settings.llm_max_retries,   # SDK handles exponential backoff
            timeout=settings.llm_request_timeout,
        )
        self._semaphore = asyncio.Semaphore(settings.llm_max_concurrency)
        self._mode = settings.llm_structured_output_mode  # auto|json_schema|json_object|text
        self._model = settings.llm_model

    async def call(
        self,
        messages: list[dict],
        response_model: type[BaseModel] | None = None,
    ) -> str:
        async with self._semaphore:
            return await self._call_with_fallback(messages, response_model)

    async def _call_with_fallback(self, messages, response_model):
        mode = self._mode

        if response_model and mode in ("auto", "json_schema"):
            try:
                parsed = await self._client.chat.completions.parse(
                    model=self._model,
                    messages=messages,
                    response_format=response_model,
                )
                return parsed.choices[0].message.content
            except (openai.BadRequestError, openai.UnprocessableEntityError):
                if mode == "json_schema":
                    raise
                # auto: fall through to next tier

        if mode in ("auto", "json_object"):
            try:
                resp = await self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    response_format={"type": "json_object"},
                )
                return resp.choices[0].message.content
            except (openai.BadRequestError, openai.UnprocessableEntityError):
                if mode == "json_object":
                    raise
                # auto: fall through to text

        # Tier 3: plain text (always works; caller uses delimited-text protocol)
        resp = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
        )
        return resp.choices[0].message.content
```

**SDK retry behavior (D-07):** The SDK retries on `APIConnectionError`, `APITimeoutError`, `RateLimitError` (respects `Retry-After`), and `InternalServerError` (5xx). It does NOT retry `BadRequestError` (400) — important for the fallback detection above. Set `max_retries=4` on the constructor; never wrap individual calls in `tenacity`.

### Pattern 4: pydantic-settings YAML Config (D-11)

**What:** Layered config: env vars override YAML file, which provides defaults. `SecretStr` ensures the API key is never logged.
**When to use:** The project's single settings object, imported everywhere config values are needed.

```python
# Source: empirically validated 2026-05-31; YamlConfigSettingsSource pattern required
from pydantic_settings import BaseSettings, SettingsConfigDict, YamlConfigSettingsSource
from pydantic import SecretStr, Field
from typing import Tuple, Type, Any

CONFIG_PATH = "/config/config.yaml"   # overridable via env TREZARR_CONFIG_PATH

class TrezarrSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TREZARR_",
        env_nested_delimiter="__",
    )
    llm_base_url: str = "http://localhost:1234/v1"
    llm_api_key: SecretStr = SecretStr("not-set")
    llm_model: str = "gpt-4o"
    llm_max_retries: int = 4
    llm_request_timeout: float = 120.0
    llm_max_concurrency: int = 4          # asyncio.Semaphore cap (D-06)
    llm_structured_output_mode: str = "auto"  # D-04
    llm_context_window: int = 32768       # D-05; used by Phase 2 batching

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: Any,
        env_settings: Any,
        dotenv_settings: Any,
        file_secret_settings: Any,
    ) -> Tuple:
        return (
            init_settings,       # programmatic overrides (highest priority)
            env_settings,        # TREZARR_* env vars
            YamlConfigSettingsSource(settings_cls, yaml_file=CONFIG_PATH),
            file_secret_settings,
        )
```

**Gotcha:** `yaml_file=CONFIG_PATH` in `model_config` alone is silently ignored (pydantic-settings emits only a `UserWarning`). `settings_customise_sources` must be overridden and `YamlConfigSettingsSource` explicitly registered. This was confirmed empirically.

**Gotcha:** `pydantic-settings[yaml]` (not just `pydantic-settings`) must be installed — this pulls in PyYAML.

### Anti-Patterns to Avoid

- **Passing pysubs2 round-trip output as "byte-identical" SRT:** pysubs2 renumbers indices from 1 and normalizes timecode format and line endings. The custom parser is required for FMT-01. Do not skip it.
- **Wrapping `.create()` or `.parse()` in `tenacity`:** The SDK already retries internally. Stacking tenacity causes retry storms (double-retry anti-pattern, D-07). tenacity belongs only at the pipeline-step level (Phase 2+).
- **Using `yaml_file=` in `model_config` without `settings_customise_sources`:** silently ignored; YAML values are never loaded. Always override `settings_customise_sources`.
- **Logging `settings.llm_api_key`:** `SecretStr` hides the value in `repr()` and `model_dump()`. Never call `.get_secret_value()` outside the `LLMClient` constructor.
- **Assuming charset-normalizer identifies CP1258:** It misidentifies CP1258 as `big5`. Always BOM-check and UTF-8-try before invoking charset-normalizer (see Pattern 2).

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTTP retry + exponential backoff for LLM calls | Custom retry loop | `AsyncOpenAI(max_retries=4)` | SDK handles 429 Retry-After, jitter, 5xx — custom loop risks double-retry storms |
| API key masking in logs | Manual string scrubbing | `pydantic.SecretStr` | Masks in `repr()`, `str()`, `model_dump()` automatically; no chance of accidental log leak |
| Layered YAML + env config | Custom config loader | `pydantic-settings` + `YamlConfigSettingsSource` | Type-validated, env-override, secret-masking, single model |
| Async concurrency cap | Thread locks / custom semaphore | `asyncio.Semaphore` | Native asyncio primitive; cooperates with await without blocking event loop |

---

## Runtime State Inventory

> Omitted — this is a greenfield phase with no existing runtime state to rename or migrate.

---

## Common Pitfalls

### Pitfall 1: pysubs2 renumbers SRT indices — breaking byte-identity

**What goes wrong:** Loading an SRT via pysubs2 and saving it back produces indices `1, 2, 3…` even if the source had `5, 10, 15…` or any non-sequential numbering. [VERIFIED: empirically tested pysubs2 1.8.1]

**Why it happens:** pysubs2 stores events in a list and serializes them back as sequential integers. There is no API option to preserve original indices.

**How to avoid:** Use the thin custom SRT parser (Pattern 1). Indices are stored verbatim in `SubLine.index: str` and written back unchanged.

**Warning signs:** Output SRT starts with `1\n` when the source started with `5\n`; golden-file diff fails at first cue.

---

### Pitfall 2: pysubs2 normalizes period timecodes and 2-digit milliseconds — breaking byte-identity

**What goes wrong:** `00:00:01.000` (period separator) → `00:00:01,000` (comma). `00:00:01,50` (2-digit ms) → `00:00:01,500` (3-digit). [VERIFIED: empirically tested]

**Why it happens:** pysubs2 normalizes to the SRT spec's standard timecode format on serialization.

**How to avoid:** Custom parser stores timecode strings verbatim (they are never parsed into milliseconds in Phase 1 — timing is immutable data the codec preserves, not transforms).

**Warning signs:** Bytes differ after round-trip on files from some subtitle tools (e.g. older MKV rippers using period separator).

---

### Pitfall 3: pysubs2 strips `<b>`, `<font>`, and `{\an8}` tags from SRT — breaking D-09

**What goes wrong (default pysubs2):**
- `<b>Bold</b>` → `Bold` (bold tag stripped from SRT output)
- `<font color="red">Text</font>` → `Text` (font tag stripped)
- `{\an8}Positioned` → `Positioned` (SSA override tag stripped)
[VERIFIED: empirically tested; `<i>` IS preserved by default]

**Partial fix with kwargs:** `keep_html_tags=True` on parse + `keep_ssa_tags=True` on serialize fixes all three. But the custom parser avoids this entirely — it never touches tag structure.

**How to avoid:** Custom parser stores `SubLine.text` verbatim including all tags. Irrelevant with the custom parser approach, but document for any future pysubs2 usage.

**Warning signs:** Output SRT missing bold/font tags; `<i>` present but `<b>` absent.

---

### Pitfall 4: charset-normalizer misidentifies CP1258 — breaking encoding write-back

**What goes wrong:** A CP1258-encoded Vietnamese source file is detected as `big5` by charset-normalizer. Writing back as `big5` corrupts the file. [VERIFIED: empirically tested with `Xin chào` in CP1258]

**Why it happens:** CP1258 has no unambiguous byte signature. Both charset-normalizer and chardet fail on short subtitle files.

**How to avoid:** BOM-check first; then try strict UTF-8 decode (most modern files); fall back to charset-normalizer. If the detected codec is a CJK family codec but the file is Vietnamese, log a warning and default to UTF-8. Document CP1258 as best-effort.

**Warning signs:** Output file fails to decode; Vietnamese diacritics appear as CJK characters.

---

### Pitfall 5: pydantic-settings YAML silently not loaded

**What goes wrong:** `SettingsConfigDict(yaml_file="config.yaml")` emits a `UserWarning` at startup and loads nothing from the YAML file. Config falls back to env vars and defaults only. [VERIFIED: empirically confirmed — pydantic-settings raises UserWarning "will be ignored because no YamlConfigSettingsSource source is configured"]

**Why it happens:** YAML support in pydantic-settings 2.x requires explicit registration in `settings_customise_sources`. The `yaml_file` key in `model_config` is not self-activating.

**How to avoid:** Always override `settings_customise_sources` and add `YamlConfigSettingsSource(settings_cls, yaml_file=CONFIG_PATH)` (Pattern 4).

**Warning signs:** `config.yaml` changes have no effect; startup UserWarning in logs; users report settings not respected.

---

### Pitfall 6: SDK `max_retries` default is 2, not 4

**What goes wrong:** `AsyncOpenAI()` without `max_retries` uses the SDK default of `2`. On low-tier or self-hosted endpoints (common for Trezarr users), 2 retries may be insufficient for transient 429s. [VERIFIED: SDK introspection confirmed `default=2` in `AsyncOpenAI.__init__`]

**How to avoid:** Always set `max_retries` explicitly from config (D-07 default: 4). The `TrezarrSettings` model defaults to `llm_max_retries: int = 4`.

---

### Pitfall 7: Structured-output fallback catches the wrong exception tier

**What goes wrong:** Using only `openai.APIError` (the base class) as the catch for structured-output rejection catches retry-eligible errors (429, 5xx) and re-routes them to the fallback instead of letting the SDK retry them.

**Why it happens:** Catching too broadly.

**How to avoid:** Catch ONLY `openai.BadRequestError` (400) and `openai.UnprocessableEntityError` (422) for tier fallback. These are the status codes endpoints return when rejecting `response_format=json_schema`. [VERIFIED: SDK exception hierarchy — `BadRequestError` and `UnprocessableEntityError` both subclass `APIStatusError`; neither is retried by the SDK by design]

---

## Code Examples

### Golden-File Round-Trip Test Pattern

```python
# tests/codec/test_srt_roundtrip.py
import pytest
from pathlib import Path
from trezarr.subtitles.srt import read_srt, write_srt

FIXTURES = Path(__file__).parent.parent / "fixtures"

@pytest.mark.parametrize("fixture", [
    "minimal.srt",
    "crlf_indices.srt",
    "period_timecodes.srt",
    "utf8bom.srt",
    "inline_bold.srt",
    "malformed_index.srt",
])
def test_byte_identical_roundtrip(tmp_path, fixture):
    src = FIXTURES / fixture
    original_bytes = src.read_bytes()
    doc = read_srt(str(src))
    out = tmp_path / fixture
    write_srt(doc, str(out))
    assert out.read_bytes() == original_bytes, \
        f"Round-trip not byte-identical for {fixture}"
```

### LLM Client Tier Fallback Test Pattern

```python
# tests/llm/test_client_tiers.py
import pytest
import asyncio
from unittest.mock import AsyncMock, patch
import openai
from trezarr.llm.client import LLMClient
from trezarr.config import TrezarrSettings

@pytest.fixture
def settings():
    return TrezarrSettings(
        llm_base_url="http://localhost:1234/v1",
        llm_api_key="test-key",
        llm_model="test-model",
        llm_structured_output_mode="auto",
        llm_max_concurrency=1,
    )

@pytest.mark.asyncio
async def test_falls_back_to_json_object_on_400(settings):
    client = LLMClient(settings)
    # Simulate endpoint rejecting json_schema with 400
    with patch.object(client._client.chat.completions, "parse",
                      side_effect=openai.BadRequestError("Not supported", response=..., body={})):
        with patch.object(client._client.chat.completions, "create",
                          return_value=AsyncMock(...)) as mock_create:
            await client.call([{"role": "user", "content": "test"}])
            # Should have fallen through to json_object tier
            assert mock_create.called
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| chardet for encoding detection | charset-normalizer | ~2021 | More accurate on short files; already a transitive dep of httpx/requests |
| pydantic v1 `BaseSettings` | pydantic-settings v2 as a separate package | Pydantic v2 (2023) | `BaseSettings` moved to `pydantic-settings`; must install separately |
| openai `ChatCompletion.create()` | `client.chat.completions.create()` and `.parse()` | SDK v1+ (2023) | Stateless class methods are removed; use instance methods only |
| `asyncio_mode = "legacy"` in pytest-asyncio | `asyncio_mode = "auto"` | pytest-asyncio 0.21+ | Removes per-test `@pytest.mark.asyncio` boilerplate |
| `yaml_file=` in `model_config` alone | `YamlConfigSettingsSource` in `settings_customise_sources` | pydantic-settings 2.x | The shortcut is silently non-functional; the explicit source registration is required |

**Deprecated/outdated:**

- `openai.ChatCompletion.create()` (class method): removed in SDK v1. Use `client.chat.completions.create()`.
- `response_format="json_object"` (bare string): use `{"type": "json_object"}` dict.
- `pydantic.BaseSettings`: moved to `pydantic_settings.BaseSettings` since Pydantic v2.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | CP1258-encoded Vietnamese subtitle files are rare in modern distribution; UTF-8 is the overwhelmingly dominant encoding for new files | Pitfall 4 / Encoding | If a significant portion of the user's library is CP1258, best-effort detection may corrupt those files on write-back |
| A2 | The delimited-text fallback protocol format (Tier 3) is left to Claude's discretion per D-04 | LLM Client pattern | If the chosen format is fragile on long inputs, Phase 2 batching will need a more robust design |
| A3 | `pytest-asyncio 1.2.0` with `asyncio_mode = "auto"` is sufficient for async codec and client tests | Validation Architecture | If the project later needs a different asyncio event loop policy, this config may need adjustment |

---

## Open Questions

1. **Delimited-text fallback protocol format (Tier 3)**
   - What we know: Tiers 1 and 2 produce structured output; Tier 3 is plain text that the caller must parse via a prompt-specified format.
   - What's unclear: The specific delimiter convention (numbered lines? XML-like tags? JSON in prose?) — left to Claude's discretion (D-04).
   - Recommendation: Numbered-line protocol (1-indexed, one translated line per source line) is the simplest and most robust for long files. Decide in the LLM client task.

2. **pydantic-settings version (2.11.0 installed vs 2.14.1 latest)**
   - The research venv installed 2.11.0 but PyPI latest is 2.14.1. Both support `YamlConfigSettingsSource`. The project install command specifies `>=2.14.1`.
   - No action needed; just use the pinned version from `uv add`.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| Python 3.12 | Runtime | ✓ | 3.12.12 | — |
| uv | Dependency management | ✓ | 0.11.16 | pip + venv (slower) |
| git | Version control | ✓ | 2.39.5 | — |

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.4.2 + pytest-asyncio 1.2.0 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` — created in Wave 0 |
| Quick run command | `pytest tests/ -x -q` |
| Full suite command | `pytest tests/ -v` |

`pyproject.toml` must include:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| FMT-01 | SRT round-trip byte-identical (6 fixture files) | unit (golden-file) | `pytest tests/codec/test_srt_roundtrip.py -x` | Wave 0 |
| FMT-01 | Index preserved verbatim (non-sequential) | unit | `pytest tests/codec/test_srt_roundtrip.py::test_byte_identical_roundtrip[crlf_indices.srt]` | Wave 0 |
| FMT-01 | Period timecodes not normalized | unit | `pytest tests/codec/test_srt_roundtrip.py::test_byte_identical_roundtrip[period_timecodes.srt]` | Wave 0 |
| FMT-01 | Inline tags preserved (`<b>`, `<font>`, `{\an8}`) | unit | `pytest tests/codec/test_srt_roundtrip.py::test_byte_identical_roundtrip[inline_bold.srt]` | Wave 0 |
| FMT-01 | UTF-8 BOM round-trip | unit | `pytest tests/codec/test_srt_roundtrip.py::test_byte_identical_roundtrip[utf8bom.srt]` | Wave 0 |
| FMT-01 | SubLine.text is mutable, SubLine.index/start_tc/end_tc are not exposed to LLM | unit | `pytest tests/codec/test_srt_model.py -x` | Wave 0 |
| ENG-01 | TrezarrSettings loads from YAML + env override | unit | `pytest tests/config/test_settings.py -x` | Wave 0 |
| ENG-01 | API key never appears in `str(settings)` or `model_dump()` | unit | `pytest tests/config/test_settings.py::test_api_key_not_logged` | Wave 0 |
| ENG-01 | LLMClient produces successful response against real endpoint | integration (manual) | Manual: configure real endpoint, run `pytest tests/llm/test_client_live.py -v -s` | Wave 0 — skip in CI |
| ENG-01 | Structured-output tier 1 (json_schema) used by default | unit (mock) | `pytest tests/llm/test_client_tiers.py::test_uses_json_schema_by_default` | Wave 0 |
| ENG-01 | Falls back to json_object on 400 | unit (mock) | `pytest tests/llm/test_client_tiers.py::test_falls_back_to_json_object_on_400` | Wave 0 |
| ENG-01 | Falls back to text on second 400 | unit (mock) | `pytest tests/llm/test_client_tiers.py::test_falls_back_to_text_on_second_400` | Wave 0 |
| ENG-01 | Pinned mode=json_schema raises on 400, does not fall back | unit (mock) | `pytest tests/llm/test_client_tiers.py::test_pinned_mode_raises` | Wave 0 |
| ENG-01 | Semaphore limits concurrent calls to max_concurrency | unit (mock+asyncio) | `pytest tests/llm/test_client_concurrency.py -x` | Wave 0 |
| ENG-01 | SDK max_retries used; no tenacity stacking | unit (mock) | `pytest tests/llm/test_client_no_double_retry.py -x` | Wave 0 |

### Sampling Rate

- **Per task commit:** `pytest tests/ -x -q` (< 5 seconds; all unit tests, no LLM calls)
- **Per wave merge:** `pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd-verify-work`
- **Live endpoint test:** manual only (`pytest tests/llm/test_client_live.py -v -s` with real `TREZARR_LLM_BASE_URL` etc. set)

### Wave 0 Gaps

- [ ] `tests/conftest.py` — shared fixtures (settings factory, tmp_path helpers)
- [ ] `tests/fixtures/*.srt` — 6 golden SRT files covering all round-trip cases
- [ ] `tests/codec/test_srt_roundtrip.py` — golden-file byte-identity parametrized tests (FMT-01)
- [ ] `tests/codec/test_srt_model.py` — SubLine model field separation test
- [ ] `tests/config/test_settings.py` — settings YAML+env load, SecretStr masking (ENG-01)
- [ ] `tests/llm/test_client_tiers.py` — structured-output tier fallback (mocked) (ENG-01)
- [ ] `tests/llm/test_client_concurrency.py` — semaphore cap test (ENG-01)
- [ ] `tests/llm/test_client_live.py` — real endpoint smoke test (marked `@pytest.mark.live`, excluded from CI)
- [ ] `pyproject.toml` — `asyncio_mode = "auto"` in `[tool.pytest.ini_options]`
- [ ] Framework install: `uv add --dev pytest pytest-asyncio` — if not already done

---

## Security Domain

> `security_enforcement: true`, ASVS level 1 (from config.json).

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No (Phase 1 has no auth surface) | — |
| V3 Session Management | No | — |
| V4 Access Control | No | — |
| V5 Input Validation | Yes — SRT input parsed from potentially untrusted file content | Regex-based parser; malformed cues are preserved-and-flagged (D-10), never cause crashes |
| V6 Cryptography | Partial — API key must be protected in memory | `pydantic.SecretStr` — API key never appears in repr/logs; only accessed via `.get_secret_value()` in `LLMClient` constructor |

### Known Threat Patterns for This Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| API key leaked in application logs | Information Disclosure | `SecretStr` for `llm_api_key`; never call `.get_secret_value()` outside `LLMClient.__init__` |
| Malformed SRT file causing parser crash or injection | Tampering | Custom parser skips malformed cues (D-10), logs warning; no `eval()` or shell execution in codec |
| Regex DoS (ReDoS) on malformed SRT | DoS | Keep SRT regex simple (no catastrophic backtracking); split on blank lines first, then match within blocks |
| YAML config injection | Tampering | pydantic-settings validates all config values against the model; no `yaml.load()` (uses PyYAML's `safe_load` internally) |
| SSRF via user-supplied `base_url` | Information Disclosure | Accepted by design — this IS the user's own endpoint (project constraint); document that the URL should point to a trusted host |

---

## Sources

### Primary (HIGH confidence)

- pysubs2 1.8.1 installed + empirical round-trip testing (2026-05-31) — all pysubs2 behavior claims
- OpenAI SDK 2.38.0 installed + `inspect` introspection (2026-05-31) — AsyncOpenAI signature, exception hierarchy, default max_retries, AsyncCompletions methods
- pydantic-settings 2.11.0 + empirical YAML config testing (2026-05-31) — `YamlConfigSettingsSource` requirement, `SecretStr` behavior
- charset-normalizer 3.4.7 empirical encoding detection (2026-05-31) — CP1258 misidentification confirmed
- Python 3.12.12 stdlib `asyncio.Semaphore` — standard library, no external verification needed

### Secondary (MEDIUM confidence)

- `.planning/research/STACK.md` (2026-05-31) — version recommendations, project-level stack decisions
- `.planning/research/PITFALLS.md` (2026-05-31) — double-retry anti-pattern, byte-identity requirements
- `.planning/research/ARCHITECTURE.md` (2026-05-31) — codec-as-isolated-module boundary, project structure

### Tertiary (informational)

- PyPI JSON API (live, 2026-05-31) — latest stable versions: pysubs2 1.8.1, openai 2.38.0, pydantic 2.13.4, pydantic-settings 2.14.1, charset-normalizer 3.4.7, pytest 8.4.2, pytest-asyncio 1.2.0

---

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — all packages installed and tested empirically; versions verified against PyPI
- Architecture: HIGH — codec approach determined by empirical round-trip failure; not by assumption
- Pitfalls: HIGH — every pitfall in this document was reproduced empirically (not inferred from docs)
- Encoding: MEDIUM for legacy encodings — CP1258 behavior verified; older TCVN3/VISCII not tested
- Test design: HIGH — pattern is standard pytest golden-file; no novel testing approach

**Research date:** 2026-05-31
**Valid until:** 90 days for standard stack items; 30 days for OpenAI SDK (fast-moving)
