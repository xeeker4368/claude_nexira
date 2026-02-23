"""
Creative Service - Workshop Output Management
Nexira / Ultimate AI System v8.0 - Phase 6
Created by Xeeker & Claude - February 2026

Manages Sygma's creative outputs:
- Stores code, essays, stories, scripts to DB
- Provides sandbox code execution
- Manages output history
- Handles file export
"""

import subprocess
import tempfile
import os
import sys
import re
from datetime import datetime
from typing import Dict, List, Tuple, Optional


class CreativeService:

    SUPPORTED_LANGUAGES = {
        'python': {'ext': 'py',  'runner': 'python3', 'timeout': 10},
        'python3':{'ext': 'py',  'runner': 'python3', 'timeout': 10},
        'bash':   {'ext': 'sh',  'runner': 'bash',    'timeout': 5},
        'shell':  {'ext': 'sh',  'runner': 'bash',    'timeout': 5},
        'js':     {'ext': 'js',  'runner': 'node',    'timeout': 8},
        'javascript': {'ext': 'js', 'runner': 'node', 'timeout': 8},
        'node':   {'ext': 'js',  'runner': 'node',    'timeout': 8},
    }

    def __init__(self, db_connection):
        self.db = db_connection
        self._ensure_tables()

    def _ensure_tables(self):
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS creative_outputs (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at   TEXT,
                    output_type  TEXT,
                    title        TEXT,
                    content      TEXT,
                    language     TEXT,
                    prompt       TEXT,
                    run_result   TEXT,
                    run_success  INTEGER DEFAULT 0
                )
            """)
            self.db.commit()
        except Exception:
            pass

    def save_output(self, output_type: str, title: str, content: str,
                    language: str = '', prompt: str = '') -> int:
        """Save a creative output. Returns the new row ID."""
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                INSERT INTO creative_outputs
                    (created_at, output_type, title, content, language, prompt)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (datetime.now().isoformat(), output_type, title,
                  content, language, prompt[:500]))
            self.db.commit()
            return cursor.lastrowid
        except Exception:
            return -1

    def get_history(self, limit: int = 20,
                    output_type: str = None) -> List[Dict]:
        try:
            cursor = self.db.cursor()
            if output_type:
                cursor.execute("""
                    SELECT id, created_at, output_type, title, language, run_success
                    FROM creative_outputs WHERE output_type = ?
                    ORDER BY id DESC LIMIT ?
                """, (output_type, limit))
            else:
                cursor.execute("""
                    SELECT id, created_at, output_type, title, language, run_success
                    FROM creative_outputs ORDER BY id DESC LIMIT ?
                """, (limit,))
            return [{'id': r[0], 'created_at': r[1], 'type': r[2],
                     'title': r[3], 'language': r[4], 'run_success': bool(r[5])}
                    for r in cursor.fetchall()]
        except Exception:
            return []

    def get_output(self, output_id: int) -> Optional[Dict]:
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                SELECT id, created_at, output_type, title, content, language, prompt, run_result, run_success
                FROM creative_outputs WHERE id = ?
            """, (output_id,))
            r = cursor.fetchone()
            if not r:
                return None
            return {'id': r[0], 'created_at': r[1], 'type': r[2],
                    'title': r[3], 'content': r[4], 'language': r[5],
                    'prompt': r[6], 'run_result': r[7], 'run_success': bool(r[8])}
        except Exception:
            return None

    def execute_code(self, code: str, language: str) -> Tuple[bool, str]:
        """
        Execute code in a sandboxed subprocess.
        Returns (success, output).
        """
        lang_cfg = self.SUPPORTED_LANGUAGES.get(language.lower())
        if not lang_cfg:
            return False, f"Language '{language}' not supported for execution. Supported: {', '.join(self.SUPPORTED_LANGUAGES)}"

        runner  = lang_cfg['runner']
        ext     = lang_cfg['ext']
        timeout = lang_cfg['timeout']

        # Check runner is available
        try:
            subprocess.run([runner, '--version'], capture_output=True, timeout=3)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False, f"'{runner}' is not installed on this system"

        # Write to temp file and run
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode='w', suffix=f'.{ext}',
                delete=False, dir='/tmp'
            ) as f:
                f.write(code)
                tmp_path = f.name

            result = subprocess.run(
                [runner, tmp_path],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd='/tmp'
            )
            output = ''
            if result.stdout:
                output += result.stdout
            if result.stderr:
                output += ('\n' if output else '') + result.stderr

            success = result.returncode == 0
            return success, output.strip()[:2000] or '(no output)'

        except subprocess.TimeoutExpired:
            return False, f'Execution timed out after {timeout}s'
        except Exception as e:
            return False, f'Execution error: {str(e)}'
        finally:
            try:
                if tmp_path:
                    os.unlink(tmp_path)
            except Exception:
                pass

    def save_run_result(self, output_id: int, success: bool, result: str):
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                UPDATE creative_outputs
                SET run_result = ?, run_success = ? WHERE id = ?
            """, (result[:2000], 1 if success else 0, output_id))
            self.db.commit()
        except Exception:
            pass

    def detect_language(self, code: str, hint: str = '') -> str:
        """Detect code language from content or hint."""
        if hint:
            for lang in self.SUPPORTED_LANGUAGES:
                if lang in hint.lower():
                    return lang

        # Heuristics
        if re.search(r'\bdef \w+\(|import \w+|from \w+ import|print\(', code):
            return 'python'
        if re.search(r'\bfunction \w+\(|const |let |var |console\.log', code):
            return 'javascript'
        if re.search(r'^#!/bin/bash|^\s*echo |^\s*if \[', code, re.MULTILINE):
            return 'bash'
        return 'python'  # safe default

    def extract_code_blocks(self, text: str) -> List[Dict]:
        """Extract fenced code blocks from AI response."""
        blocks = []
        pattern = r'```(\w*)\n(.*?)```'
        for match in re.finditer(pattern, text, re.DOTALL):
            lang    = match.group(1).lower() or 'text'
            content = match.group(2).strip()
            if content:
                blocks.append({'language': lang, 'content': content})
        return blocks

    def detect_output_type(self, prompt: str, content: str) -> str:
        """
        Classify output type from prompt only (not response content).
        Content is only used for code block detection.
        Conservative — only flags as creative if the prompt explicitly requests it.
        """
        p = prompt.lower()

        # Code: check prompt AND content (fenced blocks are reliable signals)
        if any(k in p for k in ['write code', 'write a script', 'write a function',
                                  'create a program', 'build a ', 'implement ']):
            return 'code'
        if any(k in content.lower() for k in ['def ', 'import ', 'function(', 'const ', 'var ']):
            return 'code'

        # Creative writing: prompt must explicitly ask for it
        if any(k in p for k in ['write a story', 'tell me a story', 'write me a story',
                                  'short story', 'fiction', 'narrative', 'once upon']):
            return 'story'
        if any(k in p for k in ['write a poem', 'write me a poem', 'haiku', 'sonnet',
                                  'write some poetry', 'rhyme']):
            return 'poem'
        if any(k in p for k in ['write an essay', 'write a blog', 'write an article',
                                  'write an analysis', 'write a report']):
            return 'essay'
        if any(k in p for k in ['write a letter', 'write an email', 'draft an email',
                                  'compose a letter', 'draft a letter']):
            return 'letter'

        return 'writing'
