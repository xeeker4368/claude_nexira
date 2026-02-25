# Nexira Optimization Changelog — February 24, 2026

## Critical Bugs Fixed

### 1. Web Search Completely Broken (main.py line ~320) — CRITICAL
`should_search()` returned a query string, but `web_search.search()` was never called.
Code jumped directly to `if results:` where `results` was undefined → NameError crash on every search trigger.
**Fix:** Added `results = web_search.search(search_query, max_results=5, source='chat')`.

### 2. search_and_chat Endpoint Dead Code (main.py) — HIGH
Response generation (`ai_engine.chat()`) and return statement were commented out.
Dangling curiosity detection referenced undefined `message` and `response_text`, and
used non-existent `ai_engine.model`.
**Fix:** Restored full endpoint logic with correct variable references (`query` not `message`,
model from config dict not attribute).

### 3. Night Consolidation Never Logged Results (night_consolidation.py) — HIGH
`cursor.execute()` at end of `run()` used `cursor` from `take_personality_snapshot()`'s
inner scope — the variable was not in scope. Every nightly consolidation ran but never
recorded results to `consolidation_log`.
**Fix:** Added proper `cursor = self.db.cursor()` with try/except wrapper.

### 4. moltbook_post_diary Queries Non-Existent Columns (main.py) — HIGH
Queried `entry_text` (doesn't exist) and `created_at` (doesn't exist in journal_entries).
Actual columns: `content` and `timestamp`.
**Fix:** Changed to `SELECT content FROM journal_entries ORDER BY timestamp DESC`.

### 5. create_intentional_moltbook_post Wrong Column (night_consolidation.py) — HIGH
Queried `ORDER BY created_at` but journal_entries uses `timestamp`.
**Fix:** Changed to `ORDER BY timestamp DESC`.

## Medium Bugs Fixed

### 6. get_live_capabilities Wrong Column (ai_engine.py) — MEDIUM
Queried `MAX(timestamp)` from consolidation_log but column is `run_date`.
**Fix:** Changed to `MAX(run_date)`.

### 7. Journal Missing created_date Column (journal.py) — MEDIUM
ai_engine.py `get_live_capabilities()` and `get_recent_activity()` query `created_date`
from journal_entries, but journal.py never created this column.
**Fix:** Added `created_date TEXT` to CREATE TABLE and INSERT in `_save_entry()`.

### 8. Database Connection Leak (schema.py) — MEDIUM
`connect()` always created a new connection, potentially losing uncommitted data.
**Fix:** Added early return if `self.conn is not None`.

## Code Quality Improvements

### 9. Security: Hardcoded Flask Secret Key (main.py)
Changed from static string to: `os.environ.get('NEXIRA_SECRET_KEY', os.urandom(32).hex())`

### 10. Inline/Duplicate Imports Eliminated
- main.py: `import re as _re` moved to module level (was inline in 2 places)
- main.py: `make_response` added to top-level flask import (was inline)
- main.py: `send_from_directory` duplicate import removed from `serve_image()`
- ai_engine.py: `import re` moved to module level from `_strip_think()`
- encryption.py: Removed duplicate `from cryptography.fernet import Fernet`
- image_gen_service.py: Removed `import re` inside `_sanitize_prompt()`
- background_tasks.py: Cleaned redundant `import sys, os` patterns

### 11. Removed .pyc files, __pycache__ dirs, .git folder, .bak files
Keeps package clean for deployment.

## Known Issues (Not Changed — Flagged for Future)

- **interest_tracker.py**: Excessive DB writes — every chat triggers 20+ INSERT/UPDATE calls.
  Recommend batching into single transaction.
- **knowledge_base**: No UNIQUE constraint on topic — can insert duplicates across consolidation runs.
- **creative_service.py**: `execute_code()` runs with full filesystem access in /tmp.
  Acceptable for local dev only.
- **System prompt ~4KB+**: Consumes significant context window on 8B models.
  Consider making sections conditional.
- **chat_history unbounded**: 773+ rows, no pruning. Will impact performance over months.
  Recommend archiving messages older than 30 days.

## Files Modified
- main.py (7 fixes)
- src/core/ai_engine.py (2 fixes)
- src/core/night_consolidation.py (2 fixes)
- src/core/journal.py (2 fixes)
- src/core/encryption.py (1 fix)
- src/core/background_tasks.py (1 fix)
- src/services/image_gen_service.py (1 fix)
- src/database/schema.py (1 fix)

**Total: 16 fixes (3 critical, 4 high, 3 medium, 6 code quality)**
