# Code Review: T2-T6 (472f3b9...be29fb0)

## Standards

1. **Hard violation — Python logging pattern (lambdas/extractor/handler.py)**
   - File uses both `logging.getLogger()` + `log.info()` directly AND a custom `_log()` function that wraps `_json.dumps()` with structured logging.
   - Inconsistent logging: `_log("page_fetch_error", ...)` vs direct `log.error()` calls violate the project's implicit pattern. Should use one approach uniformly.

2. **Mysterious Name — `_log` function (lambdas/extractor/handler.py, line ~30)**
   - Helper function `_log()` wraps log entry as JSON. Name doesn't indicate this is structured logging. Should be `_log_structured()` or `_json_log()`.

3. **Data Clumps — HTTP response construction (lambdas/api/get_action_items/handler.py, lambdas/api/complete_action_item/handler.py)**
   - Both Lambda handlers repeatedly construct `{"statusCode": N, "body": json.dumps(...), "headers": {"Content-Type": "application/json"}}`. Same shape appears in 3+ places. Should extract to helper `_lambda_response(code, body_dict)` (already done for `_resp()` in complete_action_item, but get_action_items duplicates inline).

4. **Primitive Obsession — HTTP error codes as magic integers (lambdas/ files)**
   - Status codes (200, 404, 500, 502) hardcoded throughout. Should define `HTTP_OK, HTTP_NOT_FOUND, HTTP_ERROR, HTTP_GATEWAY_ERROR` constants at module top.

5. **Judgment call — Repeated `_resp()` helper (lambdas/api/complete_action_item/handler.py)**
   - Helper defined and used correctly; get_action_items should use the same or a shared utility module to avoid the clump duplication noted in finding 3.

6. **Judgment call — Message Chain in mark-complete flow (frontend/src/App.jsx)**
   - Modal lifecycle: `setModalItem(item)` → `onConfirm()` → `setModalItem(null)` + conditional `setModalLoading()`. State transitions work, but tight coupling between three setState calls for one logical action is borderline Feature Envy. Acceptable for React hooks; no refactor needed.

7. **Judgment call — Divergent Change (frontend/src/App.css)**
   - 533→393 lines (shortened). File was likely edited for multiple unrelated reasons (age-bucket styling, modal, filter bar). Acceptable if each feature's styles are cohesive; no violation without seeing internal structure.

## Spec

1. **last_synced computation is incomplete**: Spec story 18 says "As a visitor, I want to see when the data was last refreshed, so that I know how current the information is." The GET /action-items handler (lines 54–58) derives last_synced as the maximum ISO datetime across open items only. If all items are marked complete and the next sync hasn't delivered new items, the dashboard shows stale or "Never" instead of the true extractor run time from _sync_meta.last_synced.

2. **CI testing incomplete for Lambda Sync and Complete endpoints**: Spec "Testing Decisions" states tests should cover "Lambda Sync: unit-test the extraction + DynamoDB write path" and "Complete Lambda: unit-test the validation guard". Test files exist (test_extractor.py, complete_action_item/tests/test_handler.py) but .github/workflows/ci.yml (lines 41–54) only runs `pytest lambdas/api/get_action_items/tests/` — the extractor and complete-action-item tests are never run in CI.

3. **Age bucket thresholds confirmed correct**: text_processing.py age_bucket() (lines 285–293) implements exactly the four buckets specified in the spec: fresh 0–7 days, aging 8–14 days, stale 15–30 days, critical >30 days. ✓

4. **Title exclusion uses exact membership, not substring**: extractor/handler.py line 45 uses `frozenset(["action items dashboard", "template"])` with case-insensitive lowercasing. A page titled "Action Items Dashboard - Archived" will not be excluded. Spec is ambiguous; this is a reasonable default but differs from case-insensitive substring match mentioned in prior reviews.

5. **Extractor put_item idempotency correct**: handler.py line 183 unconditionally writes every incomplete task each sync, but only incomplete tasks (status="incomplete") are extracted. Completed items persist in DynamoDB until mark-complete is called. Next sync won't overwrite them. ✓

---

Summary: Standards 7 findings, worst: Hard violation—inconsistent logging patterns (handler.py) undermines observability and breaks the custom `_log()` wrapper when callers use raw `log.error()` instead.; Spec 5 findings, worst: last_synced is computed from open items only, not from _sync_meta, causing incorrect freshness reporting when items are marked complete before new items arrive.
