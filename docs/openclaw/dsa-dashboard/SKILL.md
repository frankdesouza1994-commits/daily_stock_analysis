---
name: dsa-dashboard
description: Read and edit the daily_stock_analysis (DSA) dashboard, and run DSA stock analysis. Use when the user says "put this on my dashboard", "update the dashboard", "add … to the board", "remove … from the dashboard", "what's on my dashboard", or "analyze <stock> and add it to the board".
metadata:
  {"openclaw": {"requires": {"env": ["DSA_BASE_URL"]}, "primaryEnv": "DSA_BASE_URL"}}
---

# DSA Dashboard skill

## Setup (do this once if it is not done yet)

1. Save this file as `~/.openclaw/skills/dsa-dashboard/SKILL.md`.
2. In `~/.openclaw/openclaw.json`, add (merge with existing entries, do not delete others):

   ```json
   {
     "skills": {
       "entries": {
         "dsa-dashboard": {
           "enabled": true,
           "env": { "DSA_BASE_URL": "http://localhost:8000" }
         }
       }
     }
   }
   ```

   Use the user's real DSA address if it is not `http://localhost:8000`. No trailing `/`.
3. Check it works: `curl {DSA_BASE_URL}/api/health` should succeed, and `curl {DSA_BASE_URL}/api/v1/dashboard` should return JSON with `widgets` and `version`. If the dashboard URL returns 404, the DSA server is running old code: tell the user to check out branch `claude/openclaw-editable-dashboard-dnkx5o`, rebuild the web app, and restart `python main.py --serve-only`.
4. If any call returns 401 `unauthorized`, DSA has admin login enabled. Ask the user for the admin password, then log in once and reuse the cookie on every call:

   ```bash
   curl -c /tmp/dsa.cookie -X POST {DSA_BASE_URL}/api/v1/auth/login \
     -H 'Content-Type: application/json' -d '{"password":"<password>"}'
   # then add  -b /tmp/dsa.cookie  to every request below
   ```

## What the dashboard is

The user sees it in the DSA web app under **Board** (`{DSA_BASE_URL}/dashboard`). The page refreshes every 15 seconds, so your changes appear on their own. The user can also edit the board by hand, so always read it before writing.

## Workflow

1. **Always read first:** `GET {DSA_BASE_URL}/api/v1/dashboard`. Note `version` and each widget's `id`, `type` and `title`.
2. **Pick the operation.** All bodies are JSON with header `Content-Type: application/json`.
   - **Add a widget:** `POST {DSA_BASE_URL}/api/v1/dashboard/widgets`
     body `{"id": "...", "type": "...", "title": "...", "width": "...", "data": {...}}`.
     Optional `"position": 0` puts it first; otherwise it goes at the end.
     Give widgets short, stable ids (`moutai-advice`, `daily-summary`, `watchlist`) so you can update them later instead of creating duplicates.
   - **Update a widget:** `PATCH {DSA_BASE_URL}/api/v1/dashboard/widgets/{id}`.
     Send only what changes. Keys inside `data` are merged into the existing data (e.g. `{"data": {"value": "+4.1%"}}` keeps the old hint and tone). `"position": N` moves the widget.
   - **Delete a widget:** `DELETE {DSA_BASE_URL}/api/v1/dashboard/widgets/{id}?actor=openclaw&expected_version=<version>`
   - **Rename the board:** `PATCH {DSA_BASE_URL}/api/v1/dashboard` with `{"title": "...", "description": "..."}`.
   - **Rebuild the whole board:** `PUT {DSA_BASE_URL}/api/v1/dashboard` with `{"title": "...", "description": "...", "widgets": [...]}`. This replaces everything, so include every widget you want to keep. Only do this when the user asks for a full reorganization.
3. **On every write** include `"actor": "openclaw"` and `"expected_version": <version from step 1>`. Each successful write returns the full board with the new `version`; use that for your next write.
4. **409 `version_conflict`:** the user changed the board in the browser since you read it. Read it again and redo your change on the latest content. Never overwrite without re-reading.
5. **400 `validation_error`:** read `message` and fix the field (unknown type, bad tone, stock item without `code`, duplicate id, extra fields in `data`).
6. **404 `not_found`:** the widget id does not exist; re-read the board and use a real id.
7. **Afterwards** tell the user in one or two lines what you added, changed or removed, and that it is on the Board page.

## Widget types

| `type` | `data` | Use for |
|---|---|---|
| `markdown` | `{"content": "..."}` (up to 20000 chars; headings, lists, bold, tables) | Summaries, notes, analysis write-ups |
| `metric` | `{"value": "+3.2%", "hint": "optional caption", "tone": "default"}` — `tone` is one of `default`, `primary`, `success` (green/positive), `warning`, `danger` (red/negative) | One headline number or word |
| `stock_list` | `{"items": [{"code": "600519", "name": "贵州茅台", "note": "optional"}]}` (up to 100 items; `code` required) | Watchlists, picks |

Common fields: `title` (up to 120 chars), `width`: `sm` = 1/4 row, `md` = 1/2 (default), `lg` = 3/4, `full` = whole row. A board holds at most 50 widgets. Do not put any fields in `data` other than the ones listed above.

## Examples

```bash
# Read
curl {DSA_BASE_URL}/api/v1/dashboard

# Add a green metric
curl -X POST {DSA_BASE_URL}/api/v1/dashboard/widgets -H 'Content-Type: application/json' \
  -d '{"id":"pnl","type":"metric","title":"Watchlist P&L","width":"sm","data":{"value":"+3.2%","hint":"vs yesterday","tone":"success"},"actor":"openclaw","expected_version":0}'

# Change only its value
curl -X PATCH {DSA_BASE_URL}/api/v1/dashboard/widgets/pnl -H 'Content-Type: application/json' \
  -d '{"data":{"value":"+4.1%"},"actor":"openclaw","expected_version":1}'

# Add a watchlist
curl -X POST {DSA_BASE_URL}/api/v1/dashboard/widgets -H 'Content-Type: application/json' \
  -d '{"id":"watchlist","type":"stock_list","title":"Watchlist","width":"md","data":{"items":[{"code":"600519","name":"贵州茅台"},{"code":"AAPL","name":"Apple","note":"earnings Thu"}]},"actor":"openclaw","expected_version":2}'

# Delete
curl -X DELETE '{DSA_BASE_URL}/api/v1/dashboard/widgets/pnl?actor=openclaw&expected_version=3'
```

## Analyze a stock and put it on the board

1. Stock codes only (no Chinese names): A-shares 6 digits (`600519`), Hong Kong `hk` + 5 digits (`hk00700`), US tickers (`AAPL`, `BRK.B`). If the user gives a name, map it to a code or ask (e.g. 茅台 → `600519`, 腾讯 → `hk00700`).
2. `POST {DSA_BASE_URL}/api/v1/analysis/analyze` with
   `{"stock_code": "<code>", "report_type": "detailed", "force_refresh": true, "async_mode": false}`.
   This takes 2–5 minutes; use a timeout of at least 300 seconds. (`force_refresh` and `async_mode` are booleans, not strings.) A 409 means that stock is already being analyzed: wait and retry.
3. From the response use `stock_name`, `report.summary.operation_advice`, `report.summary.trend_prediction`, `report.summary.sentiment_score`, `report.summary.analysis_summary`, and `report.strategy.ideal_buy` / `stop_loss` / `take_profit`.
4. Upsert on the board, using ids based on the code so re-running updates instead of duplicating:
   - `metric` id `<code>-advice`, title `<stock_name> (<code>)`, value = `operation_advice`, hint = `Trend: <trend_prediction> · Sentiment <sentiment_score>`, tone `success` for buy/add, `danger` for sell/reduce/avoid, `warning` for alert, otherwise `primary`.
   - `markdown` id `<code>-analysis`, width `md` or `full`, content = the summary plus a small table of buy / stop-loss / take-profit.
   - If the widget id already exists (seen in step 1 of the workflow), `PATCH` it; otherwise `POST` it.
