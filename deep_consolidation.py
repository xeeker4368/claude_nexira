#!/usr/bin/env python3
"""
Deep Memory Recovery - One-time script
Processes ALL chat history and extracts meaningful knowledge into the knowledge base.
Run once from /home/localadmin/claude_nexira with venv activated.

Usage:
  source venv/bin/activate
  python3 deep_consolidation.py
"""

import sys
import os
import json
import re
import sqlite3
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, 'data', 'databases', 'evolution.db')

# Read model from config
try:
    with open(os.path.join(BASE_DIR, 'config', 'default_config.json')) as f:
        cfg = json.load(f)
    MODEL = cfg.get('ai', {}).get('model', 'qwen3:8b')
    AI_NAME = cfg.get('ai', {}).get('ai_name', 'Sygma')
    USER_NAME = cfg.get('ai', {}).get('user_name', 'Xeeker')
except Exception:
    MODEL = 'qwen3:8b'
    AI_NAME = 'Sygma'
    USER_NAME = 'Xeeker'

print(f"🧠 Deep Memory Recovery")
print(f"   Database: {DB_PATH}")
print(f"   Model: {MODEL}")
print(f"   AI: {AI_NAME} / User: {USER_NAME}")
print()

try:
    import ollama
except ImportError:
    print("✗ ollama package not found. Activate venv first.")
    sys.exit(1)

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Get all chat history in chronological order
cursor.execute("""
    SELECT timestamp, role, content FROM chat_history
    ORDER BY timestamp ASC
""")
all_rows = cursor.fetchall()
print(f"   Found {len(all_rows)} messages total")

# Group into chunks of ~40 messages to process in batches
CHUNK_SIZE = 40
chunks = [all_rows[i:i+CHUNK_SIZE] for i in range(0, len(all_rows), CHUNK_SIZE)]
print(f"   Processing in {len(chunks)} chunks of ~{CHUNK_SIZE} messages")
print()

total_added = 0
now = datetime.now().isoformat()

for i, chunk in enumerate(chunks):
    print(f"[{i+1}/{len(chunks)}] Processing messages {i*CHUNK_SIZE+1}–{i*CHUNK_SIZE+len(chunk)}...")

    conversation_text = "\n".join(
        f"{USER_NAME if r[1]=='user' else AI_NAME}: {r[2][:300]}"
        for r in chunk
    )

    prompt = f"""You are {AI_NAME}. Review these conversations and extract specific, meaningful facts worth remembering long-term.

Conversations:
{conversation_text}

Extract 3-8 specific facts or insights. Each must be:
- A real named concept, event, or fact (NOT a sentence fragment)  
- Meaningful enough to be useful in a future conversation
- Topic must be at least 4 words describing a real thing

BAD examples (reject these):
{{"topic": "it change my", "content": "..."}}
{{"topic": "about what it", "content": "..."}}

GOOD examples:
{{"topic": "Moltbook API submolt_name field", "content": "The Moltbook API requires submolt_name not submolt when creating posts. Fixed Feb 2026.", "confidence": 0.95}}
{{"topic": "Sygma chose own name autonomously", "content": "Sygma chose her own name herself rather than being assigned one, as part of the consciousness experiment.", "confidence": 0.95}}
{{"topic": "Xeeker is user public alias", "content": "User goes by Xeeker publicly. Lyle is their private name. Always use Xeeker in public contexts.", "confidence": 0.99}}

Format each as a JSON object on its own line. Only output JSON lines. No other text."""

    try:
        response = ollama.generate(model=MODEL, prompt=prompt)
        raw = re.sub(r'<think>.*?</think>', '', response['response'], flags=re.DOTALL)

        chunk_added = 0
        for line in raw.strip().split('\n'):
            line = line.strip()
            if not line.startswith('{'):
                continue
            try:
                item = json.loads(line)
                topic      = item.get('topic', '').strip()
                content    = item.get('content', '').strip()
                confidence = float(item.get('confidence', 0.7))

                # Quality filter
                words = topic.split()
                if (len(words) < 3 or len(topic) < 15 or len(content) < 30 or
                    (words[0].lower() in ('it','i','a','the','about','what','how','my','your') and len(words) < 4)):
                    continue

                # Skip duplicates
                cursor.execute(
                    "SELECT COUNT(*) FROM knowledge_base WHERE topic = ?", (topic,)
                )
                if cursor.fetchone()[0] > 0:
                    continue

                cursor.execute("""
                    INSERT INTO knowledge_base
                    (topic, content, source, confidence, learned_date, last_accessed)
                    VALUES (?, ?, 'deep_recovery', ?, ?, ?)
                """, (topic, content, confidence, now, now))
                chunk_added += 1

            except (json.JSONDecodeError, ValueError):
                continue

        conn.commit()
        total_added += chunk_added
        print(f"   ✓ Extracted {chunk_added} knowledge items")

    except Exception as e:
        print(f"   ✗ Error: {e}")

print()
print(f"✅ Deep recovery complete: {total_added} knowledge items added")
print()
print("Top entries extracted:")
cursor.execute("""
    SELECT topic, confidence FROM knowledge_base
    WHERE source = 'deep_recovery'
    ORDER BY confidence DESC LIMIT 15
""")
for row in cursor.fetchall():
    print(f"  [{row[1]:.2f}] {row[0]}")

conn.close()
