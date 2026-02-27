"""
Web Search Service - DuckDuckGo Integration
Nexira / Ultimate AI System v8.0 - Phase 6
Created by Xeeker & Claude - February 2026

Provides web search capability to Sygma:
- DuckDuckGo instant answers + web results (no API key needed)
- Search result formatting for AI context injection
- Search history logged to DB
- Used by chat, creative workshop, and curiosity queue
"""

import re
import json
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime
from typing import List, Dict, Optional


class WebSearchService:
    """DuckDuckGo-based web search. No API key required."""

    DDG_API    = 'https://api.duckduckgo.com/'
    DDG_HTML   = 'https://html.duckduckgo.com/html/'
    USER_AGENT = 'Mozilla/5.0 (compatible; Nexira/8.0)'

    def __init__(self, db_connection):
        self.db = db_connection
        self._ensure_tables()

    def _ensure_tables(self):
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS search_log (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp   TEXT,
                    query       TEXT,
                    result_count INTEGER,
                    source      TEXT,
                    top_result  TEXT
                )
            """)
            self.db.commit()
        except Exception:
            pass

    def _log(self, query: str, results: List[Dict], source: str = 'chat'):
        try:
            cursor = self.db.cursor()
            top = results[0].get('title', '') if results else ''
            cursor.execute("""
                INSERT INTO search_log (timestamp, query, result_count, source, top_result)
                VALUES (?, ?, ?, ?, ?)
            """, (datetime.now().isoformat(), query, len(results), source, top[:200]))
            self.db.commit()
        except Exception:
            pass

    def search(self, query: str, max_results: int = 5,
               source: str = 'chat') -> List[Dict]:
        """
        Search DuckDuckGo. Returns list of result dicts:
        {'title', 'url', 'snippet'}
        """
        results = []

        # Try instant answer API first
        try:
            results = self._ddg_instant(query)
        except Exception:
            pass

        # Fall back to HTML scrape if needed
        if not results:
            try:
                results = self._ddg_html(query, max_results)
            except Exception:
                pass

        results = results[:max_results]
        self._log(query, results, source)
        return results

    def _ddg_instant(self, query: str) -> List[Dict]:
        """DuckDuckGo Instant Answer API."""
        params = urllib.parse.urlencode({
            'q':      query,
            'format': 'json',
            'no_html': '1',
            't':      'Nexira'
        })
        req = urllib.request.Request(
            f'{self.DDG_API}?{params}',
            headers={'User-Agent': self.USER_AGENT}
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode('utf-8'))

        results = []

        # Abstract (best single answer)
        if data.get('AbstractText'):
            results.append({
                'title':   data.get('Heading', query),
                'url':     data.get('AbstractURL', ''),
                'snippet': data['AbstractText'][:400]
            })

        # Related topics
        for topic in data.get('RelatedTopics', [])[:4]:
            if isinstance(topic, dict) and topic.get('Text'):
                url = topic.get('FirstURL', '')
                results.append({
                    'title':   topic['Text'][:80],
                    'url':     url,
                    'snippet': topic['Text'][:300]
                })

        return results

    def _ddg_html(self, query: str, max_results: int) -> List[Dict]:
        """Scrape DuckDuckGo HTML results."""
        params = urllib.parse.urlencode({'q': query, 'b': ''})
        req = urllib.request.Request(
            f'{self.DDG_HTML}',
            data=params.encode(),
            headers={
                'User-Agent': self.USER_AGENT,
                'Content-Type': 'application/x-www-form-urlencoded'
            }
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode('utf-8', errors='replace')

        results = []
        # Extract result blocks
        blocks = re.findall(
            r'<a class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?'
            r'<a class="result__snippet"[^>]*>(.*?)</a>',
            html, re.DOTALL
        )
        for url, title_html, snippet_html in blocks[:max_results]:
            title   = re.sub(r'<[^>]+>', '', title_html).strip()
            snippet = re.sub(r'<[^>]+>', '', snippet_html).strip()
            # Decode HTML entities
            for ent, char in [('&amp;','&'),('&lt;','<'),('&gt;','>'),('&#x27;',"'"),('&quot;','"')]:
                title   = title.replace(ent, char)
                snippet = snippet.replace(ent, char)
            if title and snippet:
                results.append({'title': title, 'url': url, 'snippet': snippet[:300]})

        return results

    def format_for_prompt(self, query: str, results: List[Dict]) -> str:
        """Format search results for injection into AI system prompt."""
        if not results:
            return f"<<LIVE_SEARCH_EMPTY: '{query}'>>"

        lines = [f"<<LIVE_SEARCH_RESULTS for: '{query}'>>"]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r['title']}")
            lines.append(f"   {r['snippet']}")
            if r.get('url'):
                lines.append(f"   Source: {r['url']}")
        lines.append("<<END_LIVE_SEARCH — integrate this information naturally, do not reproduce these tags>>")
        return '\n'.join(lines)

    def get_history(self, limit: int = 20) -> List[Dict]:
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                SELECT timestamp, query, result_count, source, top_result
                FROM search_log ORDER BY id DESC LIMIT ?
            """, (limit,))
            return [{'timestamp': r[0], 'query': r[1], 'count': r[2],
                     'source': r[3], 'top': r[4]} for r in cursor.fetchall()]
        except Exception:
            return []

    def should_search(self, message: str) -> Optional[str]:
        """
        Detect if a message needs web search. Returns search query or None.
        Conservative — only fires on clear, unambiguous search intent.

        Key rules:
        - Must start with or be primarily a question/request, not a statement
        - Minimum length to avoid matching conversational phrases
        - Extracts a clean query rather than passing the raw message
        """
        msg = message.lower().strip()

        # Never search on short messages or pure statements
        if len(msg) < 15:
            return None

        # Never search if message looks like a directive or statement
        # (starts with "I", "Right now", "The", "This", "That", etc.)
        statement_starters = (
            "i ", "i'", "right now", "the ", "this ", "that ", "these ",
            "just ", "no more", "already", "it ", "we ", "you ", "she ",
            "he ", "they ", "there ", "here ", "when ", "while "
        )
        if any(msg.startswith(s) for s in statement_starters):
            return None

        # Explicit search commands — extract clean query after the trigger
        explicit_triggers = {
            'search for ':        'search for ',
            'search the web for ': 'search the web for ',
            'look up ':           'look up ',
            'google ':            'google ',
            'find the latest ':   'find the latest ',
            'what is the latest ': 'what is the latest ',
            'current news about ': 'current news about ',
            'news about ':        'news about ',
            'stock price of ':    'stock price of ',
            'bitcoin price':      None,
            'btc price':          None,
            'crypto price':       None,
            "what's the weather": None,
            'weather in ':        'weather in ',
            'latest version of ': 'latest version of ',
        }
        for trigger, strip_prefix in explicit_triggers.items():
            if trigger in msg:
                if strip_prefix:
                    idx = msg.find(strip_prefix) + len(strip_prefix)
                    query = message[idx:].strip()
                else:
                    query = message.strip()
                # Clean filler words
                for filler in ['can you ', 'please ', 'could you ', 'i need you to ']:
                    if query.lower().startswith(filler):
                        query = query[len(filler):]
                return query.strip()[:120] if len(query) > 3 else None

        # Questions starting with who/what/when/where about CURRENT status only
        current_markers = [
            'who is the current ', 'who won the ', 'who won last ',
            "what's the current ", "what is the current ",
            'what is the price of ', "what's the price of ",
            'live score', 'breaking news',
        ]
        for phrase in current_markers:
            if msg.startswith(phrase) or msg.startswith('what ' + phrase):
                return message.strip()[:120]

        return None
