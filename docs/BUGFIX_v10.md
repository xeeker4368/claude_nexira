# Nexira v10 — Bug Fix Release
**Date:** February 26, 2026  
**Authors:** Xeeker & Claude

## Bugs Fixed

### BUG-01 — `/api/health` route missing
**Symptom:** Health panel threw "Unexpected token <" — Flask was returning a 404 HTML page because the route didn't exist.  
**Fix:** Added `/api/health` endpoint to `main.py` with full system checks: Ollama connectivity, database, scheduler, disk space, consolidation log, and recent errors.

### BUG-02 — Journal entries stopped after Feb 23
**Symptom:** Consolidation ran nightly but wrote 0 journal entries since Feb 23.  
**Root cause:** `journal.py` still used bare `ollama.generate()` instead of `get_ollama_client()`. On any non-default `ollama_url` config, calls failed silently.  
**Fix:** Both `write_daily_reflection()` and `write_philosophical_entry()` now use `get_ollama_client(self.config)`. Also added `<think>` block stripping for qwen3 compatibility.

### BUG-03 — Curiosity queue stuck with wrong descriptions
**Symptom:** Queue items accumulating but not processing correctly; descriptions were philosophical text not research summaries.  
**Root cause:** `curiosity_engine.py` `extract_curious_topics()` used bare `ollama.generate()` — LLM extraction failing, falling back to regex path.  
**Fix:** Now uses `get_ollama_client(self.config)`.

### BUG-04 — Night consolidation ran twice on Feb 25
**Symptom:** Two consolidation_log entries for the same date.  
**Root cause:** Race condition — scheduler fires every 30s, two ticks at 02:00:03 and 02:00:09 both passed `should_run_tonight()` before either committed to the log.  
**Fix:** `should_run_tonight()` now inserts a placeholder row immediately on claiming the run slot, preventing any second attempt from passing the check.

### BUG-05 — Email "Topics Researched" showing wrong data
**Symptom:** Section showed Sygma's own philosophical writing, not actual search results. Label implied web searches occurred.  
**Fix:** Section renamed "Curiosity Queue — Researched". Added 🌐/🧠 indicator per item showing whether research was web-assisted or model-only. Query now joins `knowledge_base` to retrieve source.

### BUG-06 — Email "Conversations" showing hub relay messages as duplicates
**Symptom:** `[Operator]: Hey Sigma...` messages appearing 4x in the email conversation highlights.  
**Fix:** `chat_history` query in email composer now filters out messages matching `[%]:%` pattern (hub relay format).

### BUG-07 — Goals stuck at 100% with status 'active' permanently
**Symptom:** "Build a knowledge base of 50 topics" and "Have 100 meaningful conversations" both at 100% but never completing.  
**Root cause:** `tick_knowledge_goals()` and `tick_conversation_goals()` updated `progress` but never checked for completion.  
**Fix:** Both methods now query for goals at 100% progress and transition them to `status='completed'`, triggering `_on_goal_completed()` to generate the next goal.

### BUG-08 — Web search firing on user messages / document uploads
**Symptom:** Sygma searched Xeeker's own message text verbatim. Search triggered during normal conversation and when documents were uploaded.  
**Root cause:** `should_search()` had broad trigger phrases that matched conversational statements.  
**Fix:** Rewrote `should_search()` with statement-starter filtering (messages beginning with "I", "Right now", "The", etc. are never searched), cleaner trigger extraction, and minimum length guard. Now extracts clean query strings rather than passing raw message.

### BUG-09 — Config validator writing INFO noise to error_log
**Symptom:** Every restart produced 3-4 "Config validation passed" entries in the error log.  
**Fix:** Successful validations now print to console only. Only actual warnings and errors are written to the DB `error_log`.

### BUG-10 — Sygma losing first-person identity mid-conversation
**Symptom:** Sygma addressed herself in third person ("Have you had a chance to review it yet, Sygma?"), slipping into a narrator/facilitator voice.  
**Root cause:** `ai_engine.chat()` used `client.generate()` with conversation history injected as text into the system prompt. The model read history as a transcript rather than experiencing it as turns it participated in, causing identity drift in longer conversations.  
**Fix:** Switched to `client.chat()` with a proper messages array. System prompt provides identity/context; recent messages are passed as actual `user`/`assistant` turns. Removed duplicate conversation history from system prompt to eliminate the distancing "RECENT CONVERSATION" block.

## Files Modified
- `main.py` — Added `/api/health` route
- `src/core/ai_engine.py` — `generate()` → `chat()`, removed history from system prompt
- `src/core/journal.py` — `ollama.generate()` → `get_ollama_client()`
- `src/core/curiosity_engine.py` — `ollama.generate()` → `get_ollama_client()`
- `src/core/night_consolidation.py` — Race condition fix in `should_run_tonight()`
- `src/core/goal_tracker.py` — Completion transitions in `tick_knowledge_goals()` and `tick_conversation_goals()`
- `src/services/web_search_service.py` — Rewrote `should_search()` with statement filtering
- `src/services/email_service.py` — Hub message filter, Topics section label, source indicator
- `src/services/config_validator.py` — Suppress INFO from error_log
