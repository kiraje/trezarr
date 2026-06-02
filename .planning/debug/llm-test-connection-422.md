---
slug: llm-test-connection-422
status: resolved
trigger: "cant add llm endpoint (screenshot: Test Connection -> POST /api/test/llm: 422)"
created: 2026-06-02
updated: 2026-06-02
---

# Debug Session: llm-test-connection-422

## Symptoms

- **Expected behavior:** In the Settings UI "LLM Endpoint" card, filling Base URL +
  Model + API Key and clicking "Test Connection" should call the backend, which
  probes the user's OpenAI-compatible endpoint and returns success (or a
  connection-specific failure message).
- **Actual behavior:** The request fails immediately with `POST /api/test/llm: 422`
  (HTTP 422 Unprocessable Entity). The connection is never actually tested; the
  request is rejected at the validation boundary.
- **Error messages:** `× POST /api/test/llm: 422`
- **Timeline:** Unknown (not stated). Treat as "test connection has never worked
  with this UI build" until evidence says otherwise.
- **Reproduction:**
  1. Open Settings → LLM Endpoint.
  2. Base URL = `https://api.tlemons.com/v1`, Model = `ds/deepseek-v4-pro`, API Key set.
  3. Click "Test Connection".
  4. Observe red `POST /api/test/llm: 422`.

## Initial Analysis

HTTP 422 from FastAPI almost always means **request-body validation failed**:
the JSON the frontend POSTs to `/api/test/llm` does not match the Pydantic
model the route declares. Prime suspects:
- Frontend/backend field-name or shape mismatch (e.g. `base_url` vs `baseUrl`,
  or wrapping/not wrapping the payload).
- API key handled as "set" (masked) rather than sent — the test endpoint may
  require a key field the UI omits when the stored key is reused.
- A required field the UI doesn't send (model/base_url) or an extra/typed field.
This is deterministic and code-readable; the 422 detail body will name the
exact field.

## Current Focus

- hypothesis: CONFIRMED — Request payload sent to `POST /api/test/llm` uses
  UI-prefixed field names (`llm_base_url`, `llm_model`, `llm_api_key`) that do
  not satisfy the endpoint's `LLMTestParams` model (`base_url`, `model`,
  `api_key`), producing a 422 (three `missing` errors) before any connection
  attempt.
- test: DONE — read route handler + model, read frontend caller, reproduced 422
  with the real frontend payload shape.
- expecting: A concrete field-name mismatch. CONFIRMED.
- next_action: fix applied
- reasoning_checkpoint:
- tdd_checkpoint:

## Evidence

- timestamp: 2026-06-02
  finding: Backend route `POST /api/test/llm` declares `LLMTestParams` requiring
    exactly three REQUIRED string fields — `base_url`, `api_key`, `model`.
  source: trezarr/web/routes/test_connection.py:44-49, :177-178

- timestamp: 2026-06-02
  finding: Frontend posts the raw section-state object `llmFields` verbatim. Its
    keys are UI-PREFIXED: `llm_base_url`, `llm_model`, `llm_api_key`. The generic
    `testConnection(svc, params)` client `JSON.stringify(params)` passes them
    unmapped. The same defect exists for sonarr/radarr/bazarr cards
    (`sonarr_host` vs `host`, `sonarr_port` vs `port`, `sonarr_api_key` vs
    `api_key`).
  source: frontend/src/pages/Settings.tsx:156-160 (llmFields shape), :298
    (`<ConnectionTestButton svc="llm" params={llmFields} />`),
    frontend/src/api/client.ts:66-77 (testConnection passes params unmapped)

- timestamp: 2026-06-02
  finding: REPRODUCED deterministically. POSTing the real frontend shape
    `{llm_base_url, llm_model, llm_api_key}` to `/api/test/llm` returns HTTP 422
    with detail = three `{"type":"missing"}` errors for `body.base_url`,
    `body.api_key`, `body.model`. This exactly matches the screenshot
    `POST /api/test/llm: 422` (the error string is produced by client.ts:75
    `POST /api/test/${svc}: ${resp.status}`).
  source: ASGITransport repro via trezarr.web.app.create_app()

- timestamp: 2026-06-02
  finding: Existing backend tests POST the CORRECT unprefixed shape
    (`{base_url, api_key, model}`) directly, so they pass and never exercised the
    real UI payload — the contract gap was invisible to the test suite.
  source: tests/web/test_connection_tests.py:107 (test_llm_connection_ok)

## Eliminated

- timestamp: 2026-06-02
  ruled_out: "Masked/reuse-stored-key omits a required field" — the api_key field
    IS sent (as empty string when masked), and `api_key: str` would accept "".
    The 422 fires on field-NAME mismatch (`llm_api_key` vs `api_key`), not on the
    key value. Empty-key handling is a downstream concern, not the 422 cause.

- timestamp: 2026-06-02
  ruled_out: "Wrong type on a field (e.g. port as string)" — for LLM all three
    fields are strings; no type mismatch. (Pydantic v2 also coerces numeric port
    strings for the arr endpoints, verified.)

## Resolution

- root_cause: The Settings UI stores each section's form state under UI-prefixed
  keys (`llm_base_url`, `llm_model`, `llm_api_key`) and passed that object
  unmapped to the generic `testConnection(svc, params)` client, which POSTs it
  verbatim. The backend `LLMTestParams` model requires unprefixed names
  (`base_url`, `model`, `api_key`), so FastAPI/Pydantic rejected the body with
  HTTP 422 (`missing` for all three fields) before any LLM connection was
  attempted. The same prefix mismatch affected the Sonarr/Radarr/Bazarr test
  buttons.
- fix: In `frontend/src/api/client.ts`, `testConnection` now strips the leading
  `${svc}_` prefix from every param key before POSTing, mapping `llm_base_url →
  base_url`, `sonarr_host → host`, etc. Single-point fix repairs all four service
  test buttons. Added backend regression test posting the exact prefixed shape to
  prove it no longer 422s, plus a frontend unit test asserting the prefix is
  stripped.
- prevention: Connection-test request bodies are now built by a key-mapping layer
  rather than passing raw form-state objects; tests now exercise the real UI
  payload shape (prefixed) end-to-end so the contract gap cannot silently
  reappear.
