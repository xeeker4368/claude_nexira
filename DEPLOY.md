# Nexira Hub-Ready Changes

## Files changed
- main.py — /api/chat extended, hub endpoints added, hub replica helper
- src/core/ai_engine.py — platform/sender isolation, importance weighting, hub context in system prompt
- src/core/curiosity_engine.py — scan_hub_replica() added

## Deploy instructions
Replace these files only. Do NOT touch data/ or config/.

## What changed
1. /api/chat now accepts `platform` and `sender` params from Hub
2. Hub messages stored with platform tag, isolated from active context
3. Sygma's active conversation context only includes main_ui messages
4. Importance weighting: Lyle=1.0, hub AI=0.6, rejection=0.8, system=0.3
5. System prompt injects hub session context when platform != main_ui
6. Web search checks hub_replica.db before hitting web during hub sessions
7. New endpoints: /api/hub/replica, /api/hub/event, /api/workspace/read, /api/workspace/write
8. Curiosity engine scans hub replica on receipt, tags as hub_collaboration
9. hub_entities table auto-created in evolution.db to track other AI identities

## Safe to deploy
These changes are backward compatible. All existing behavior preserved.
The platform param defaults to main_ui if not provided.
