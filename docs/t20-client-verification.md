# T20 client-only local verification — t_170a0ded

Status: LOCAL_IMPLEMENTATION verified with mocked responses and a dependency-free DOM harness. LIVE_ACCEPTANCE=PENDING in t_7bcccf7e after separately authorized protected deployment. No deployment or GitHub push performed. Changes remain uncommitted for integrated review; existing implementation commits are preserved.

## Scope and decisions

The source repository is `/Users/achyuth/Hermes-workspace/projects/github-portfolio/hermes-job-hunter`; the assigned scratch directory was empty. T17's existing action contract was read before implementation. Only client files and this report were edited by this card. API/storage/Telegram changes in the shared tree belong to sibling cards.

- One generated UUID v4 and immutable request body per logical action, including `source: "ui"` and `client_ts`. Explicit network/5xx retries reuse that exact body/key. Duplicate pending clicks share one promise/request.
- Different roles send concurrently. Same-role requests serialize in click order while all pending mutations are visible immediately. An authoritative base plus pending overlays prevents an older response or failed action from overwriting newer actions. Removing a failed overlay never restores the entire dataset.
- Success adopts the returned role, normalizing exporter `fit_score` and `notes`. Interested column uses `routed === 'int' || status === 'interested'`. Reconciliation renders the active route immediately.
- 409 with a valid authoritative `role` replaces the base and reapplies later pending changes, silently per T17. 409 without usable state rolls back the failed overlay and shows a review instruction.
- 4xx/5xx/network errors roll back the affected overlay and show an accessible, fixed-position toast. Only allowlisted error codes or generated HTTP codes appear; server messages/stacks/hosts are not echoed. Network/5xx failures offer an actual Retry button. Superseded retries cannot overwrite subsequent actions. Retry expires conservatively 60 seconds after action creation, requiring reload/review rather than risking an expired idempotency write.
- Pipeline status controls, Role Detail status/notes controls, Backgrounder notes Save, and Focus gate buttons share the client. Contract payloads are marks/view `{}`, notes `{notes}`, and gates `{gate}`. Notes update nested strategy state without mutating the prior snapshot. Gate buttons are no longer hard-coded as completed.
- This existing bundle is public/synthetic: all POSTs target `/api/action?mode=sandbox`, with no credential headers, no caller-selected mode, no CSV access. The server must enforce its independently configured sandbox store; the query is not authorization. Authenticated personal UI routing is not introduced here.
- Action responses pass the existing public PII guard before adoption. Responses for a different role ID are rejected.

## Identifier safety

The embedded offline dataset uses r01–r50, while the canonical sandbox seed has integer IDs and different role ordering (r01 is Notion, seed ID 1 is Mercury). Guessing rNN→N would mutate another role. Offline sample actions therefore show an explicit read-only/reload notice and send NO POST. Loaded canonical numeric-string IDs convert to positive safe integers at the API boundary; unknown/nonnumeric identifiers are not repaired. Fixtures explicitly own integer IDs, and never assert a production fallback mapping.

## Changed files

- ui/app.js
- ui/styles.css
- ui/tests/test_app.py
- ui/tests/test_optimistic_actions.py (new)
- ui/tests/action_client_harness.cjs (new)
- docs/t20-client-verification.md (this report)

## Reproducible checks

From the repository:

    python3 -m unittest ui.tests.test_optimistic_actions ui.tests.test_app -v
    node --check ui/app.js
    node --check ui/tests/action_client_harness.cjs
    git diff --check

Executed result: 84 tests ran in 4.177s; OK, one pre-existing DesignTokenTests skip because docs/design-tokens.md is absent. Node syntax checks and Git whitespace check exited 0. The new suite has 14 checks covering immediate DOM movement, authoritative/exporter reconciliation, HTTP 400/404/401/429/500/503 failures, actual Retry-button behavior with identical bodies, duplicate clicks, cross-role concurrency, same-role ordered pending overlays across success/failure/conflict, 409 state, notes/gates controls, all seven supported action names, sandbox routing/UUID/no credentials, unsafe responses, offline read-only safety, expired retries, and superseded retries.

The harness executes the actual app in Node with a small DOM implementation and deferred mocked fetch responses; it is not a browser screenshot or a deployed write. Legacy tests that manually fabricated server replay or sent payload.note have been replaced with the actual client checks and plural payload.notes.

## Remaining integrated/release gates

- t_96813bb2 owns API/client/Telegram integration and root progress reporting. Re-run API validation, mode isolation, audit, persistence, and client checks together. Server response validation may supply top-level error_code; the client supports it and the nested T17 error code.
- Server sandbox enforcement and personal authorization must remain fail-closed. A query parameter alone cannot guarantee store isolation. No real API, token, Vercel write, operator tracker, or private endpoint was exercised by this card.
- API/storage limitations, audit persistence, cross-instance idempotency and cache behavior are sibling findings; client mock tests do not waive them.
- Client pending/retry state is memory-only, not durable across reloads; exact-once across runtime instances is not claimed. This public bundle does not contain an operator token-entry flow.
- Full deployed/browser acceptance, visual toast styling, protected deployment and real POST→GET round trip remain PENDING in t_7bcccf7e. No deployment was attempted.

Hotspot: ui/app.js — shared client source previously touched by T19/T20; this card changed only the client action path, gate controls, immediate rendering, and associated adapter/helper corrections. Do not recommit sibling API/Telegram changes as part of this diff.
