# 06 — Local Interface (CLI + localhost pages)

Local-first: `super` CLI owns the loop and the locks; a localhost page shows the pictures. Same back room, two faces. No fork, no cloud, works on Mac/PC/Linux.

## Architecture

- `super` CLI in any terminal (Warp, iTerm, Windows Terminal): runs jobs, enforces gates, prints `open http://127.0.0.1:4311/?token=...`.
- Local server on `127.0.0.1` only + per-run token: serves API + static pages. No LAN, no cloud. Token in URL + header; port auto-bumps on conflict.
- Optional thin VS Code plug-in later: status + "open dashboard" button only. No enforcement in the plug-in.
- Later wrap: same pages in Tauri for a desktop icon. No rewrite.
- CLI-only fallback: every action on the pages also exists as a CLI flag (`--approve`, `--tree`, `--report`) for SSH / broken-browser days.

Production API: `GET /tree`, `GET /job?id`, `POST /approve`, `POST /waive`, `GET /report`, `GET /ledger`. All read from `.super/` sqlite (job tree, gate log, issues).

## Page 1 — Job tree (where are we?)

```
+--------------------------------------------------+
| SUPER  goal: fix login bug        [report] [?]   |
+--------------------------------------------------+
| TREE                | DETAILS                    |
| v Goal: fix login   | Card B1: change pw check   |
|   v A: find cause   | Why: serves B (fix it)     |
|     * A1 done [ok]  | Needs: A2 reproduced [ok]    |
|     * A2 done [ok]  | Done = test login_fail shown |
|   > B: fix it       | Proof: link to green run     |
|     * B1 doing...   | Files: auth.py:42, test_...  |
|     - B2 waiting    | [Approve] [Ask to fix]       |
|   - C: prove it     |                            |
+--------------------------------------------------+
| Bottom bar: 3/7 proven | gate log tail | issues: 1 |
+--------------------------------------------------+
```

Components: expandable tree (depth = parent/child, badges = proven/doing/waiting/blocked); details card (what / why / needs / done-looks-like / proof link / files); bottom bar (proven count, last gate decisions, open issues). Clicking a node loads its card; clicking proof jumps to the green run. Model sees one leaf; human sees the forest.

## Page 2 — Approve (is this safe?)

```
+--------------------------------------------------+
| Approve?  B1: change password check    RISK: high|
+--------------------------------------------------+
| CRITIC SAYS (first, never builder summary):      |
| "No rate-limit on retries — brute-forceable."    |
| Blast: auth.py + login API | rollback: 1 click  |
+--------------------------------------------------+
| DIFF (Monaco view, syntax colors):               |
| - if pw == hash: ...  + if safe_eq(...) + limit  |
+--------------------------------------------------+
| Checks: type ok | tests 12/12 | secrets ok       |
|         perf +3ms | docs updated? NO [waive?]     |
+--------------------------------------------------+
| [Approve] [Approve with note] [Send back to fix] |
+--------------------------------------------------+
```

Rules: critic objection first; builder summary never shown; diff + checks + blast radius + rollback always visible; big/new/auth/billing/crypto always requires this screen (small + proven auto-passes, logged). Every decision writes to the ledger with who + why.

## Page 3 — Report card (what was proven?)

```
+--------------------------------------------------+
| Done: fix login bug     Score: 6/7 proven        |
+--------------------------------------------------+
| Per job: A1 ok | A2 ok | B1 ok | B2 waived (expiry|
|  2026-10-01, owner: you) | C1 ok                |
+--------------------------------------------------+
| Evidence: test links, perf +3ms, sink-audit clean|
| Waivers: 1 (docs, expires, visible)              |
| Revert: [revert B1] [revert all after A2]        |
+--------------------------------------------------+
```

Shows per-job proof links, waivers with expiry + owner, evidence (tests, perf diff, audit), revert buttons (single job or range). This page is the audit trail — "looks good" never appears without a link.

## Build order

1. CLI + `/tree` + Page 1 read-only. Prove the tree replaces the 1D todo.
2. Add `/approve` + Page 2. Prove approvals carry evidence.
3. Add `/report` + Page 3. Prove done means linked, not said.
4. Polish: token auth, port handling, CLI flags parity, then optional plug-in / Tauri wrap.
