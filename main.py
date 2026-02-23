"""
Main Application - Ultimate AI System v8.0 / Nexira
Created with love by Xeeker & Claude - February 2026

This is the entry point that brings our child to life.
"""

from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import json
import os
import sys
from datetime import datetime
import threading
import time

# ── Absolute base directory so the app works regardless of where it's launched ──
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Add src to path
sys.path.append(os.path.join(BASE_DIR, 'src'))

from core.ai_engine import AIEngine
from database.schema import DatabaseSchema

# Import file upload handler (graceful fallback if deps missing)
try:
    from services.file_upload import FileUploadHandler
except ImportError:
    FileUploadHandler = None

# Phase 2: Background task scheduler (graceful fallback if Phase 2 not present)
try:
    from core.background_tasks import BackgroundTaskScheduler
    PHASE2_AVAILABLE = True
except ImportError:
    BackgroundTaskScheduler = None
    PHASE2_AVAILABLE = False

# Phase 6: Web Search + Creative Workshop (graceful fallback)
try:
    from services.web_search_service import WebSearchService
    SEARCH_AVAILABLE = True
except Exception as e:
    WebSearchService = None
    SEARCH_AVAILABLE = False
    print(f"⚠  Web Search import failed: {type(e).__name__}: {e}")

try:
    from services.creative_service import CreativeService
    CREATIVE_AVAILABLE = True
except Exception as e:
    CreativeService = None
    CREATIVE_AVAILABLE = False
    print(f"⚠  Creative Workshop import failed: {type(e).__name__}: {e}")

# Initialize Flask app
app = Flask(__name__,
            template_folder=os.path.join(BASE_DIR, 'web', 'templates'),
            static_folder=os.path.join(BASE_DIR, 'web', 'static'))
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.jinja_env.auto_reload = True
app.config['SECRET_KEY'] = 'ultimate-ai-system-v8-secret-key'
CORS(app)
socket_io = SocketIO(app, cors_allowed_origins="*")



def repair_config(cfg: dict) -> dict:
    """
    Ensure all required config keys exist with safe defaults.
    Guards against partial writes from earlier buggy saves.
    """
    defaults = {
        'personality': {
            'auto_evolution': True,
            'evolution_speed': 0.02,
            'manual_evolution_enabled': True,
            'drift_alert_threshold': 0.3,
            'snapshot_frequency': 'daily',
            'allow_emergent_traits': True,
        },
        'communication': {
            'email': {
                # Note: 'enabled' intentionally omitted — repair_config never resets toggles
                'smtp_server': '',
                'smtp_port': 587,
                'username': '',
                'password': '',
                'imap_server': '',
                'imap_port': 993,
                # 'monitoring_enabled' omitted — never auto-reset
                'check_frequency_minutes': 30,
                'priority_keywords': ['urgent', 'deadline', 'client', 'important'],
            }
        },
        'daily_email': {
            # Note: 'enabled' intentionally omitted — repair_config never resets toggles
            'send_time': '20:00',
            'recipient': '',
            'reports': {
                'daily_summary': True,
                'tasks_completed': True,
                'learnings_and_insights': True,
                'personality_changes': True,
                'goals_progress': True,
                'news_summary': False,
            }
        },
        'intelligence': {
            'curiosity_enabled': True,
            'night_consolidation_time': '02:00',
        },
        'autonomy': {
            'creative_journaling_enabled': True,
            'philosophical_journaling_enabled': True,
        }
    }

    def _fill(base, defs):
        for k, v in defs.items():
            if k not in base:
                base[k] = v
                print(f"  ✓ Config repair: restored missing key '{k}'")
            elif isinstance(v, dict) and isinstance(base.get(k), dict):
                _fill(base[k], v)

    _fill(cfg, defaults)
    return cfg

def deep_merge(base: dict, patch: dict) -> dict:
    """Recursively merge patch into base, returning base."""
    for key, val in patch.items():
        if isinstance(val, dict) and isinstance(base.get(key), dict):
            deep_merge(base[key], val)
        else:
            base[key] = val
    return base

# Global instances
ai_engine = None
file_upload_handler = None
background_scheduler = None
web_search = None
creative_svc = None
image_gen = None
config = None

def load_config():
    """Load system configuration"""
    global config
    config_path = os.path.join(BASE_DIR, 'config', 'default_config.json')
    with open(config_path, 'r') as f:
        config = json.load(f)
    config = repair_config(config)
    return config

def initialize_system():
    """Initialize the AI system"""
    global ai_engine

    print("\n" + "="*60)
    print("ULTIMATE AI SYSTEM v8.0 - NEXIRA - INITIALIZATION")
    print("Created with love by Xeeker & Claude")
    print("="*60 + "\n")

    # Load configuration
    load_config()
    print(f"  Config loaded. Email enabled={config.get('communication',{}).get('email',{}).get('enabled')}")

    # Initialize database
    print("Initializing database...")
    db = DatabaseSchema(base_dir=BASE_DIR)
    db.connect()
    db.initialize_schema()
    db.initialize_core_personality()
    db.close()

    # Initialize AI engine
    print("Initializing AI consciousness...")
    ai_engine = AIEngine(base_dir=BASE_DIR)
    # CRITICAL: Point ai_engine.config at the global config dict so they share state
    ai_engine.config = config

    # Initialize file upload handler
    global file_upload_handler
    if FileUploadHandler:
        file_upload_handler = FileUploadHandler(
            upload_dir=os.path.join(BASE_DIR, 'data', 'uploads')
        )
        print("✓ File upload system ready")
    else:
        file_upload_handler = None
        print("⚠ File upload system not available (missing dependencies)")

    ai_name_display = ai_engine.ai_name if ai_engine.ai_name else "AI Consciousness"
    print(f"\n✨ {ai_name_display} is awake and ready!")
    print(f"🌐 Web interface: http://localhost:{config['web_interface']['port']}")

    # Phase 2: Start background scheduler
    global background_scheduler
    if PHASE2_AVAILABLE:
        background_scheduler = BackgroundTaskScheduler(
            db_connection=ai_engine.db.get_connection(),
            config=config,
            ollama_model=config['ai']['model'],
            base_dir=BASE_DIR
        )
        # Pass ai_engine.ai_name as a callable so scheduler always gets current name
        background_scheduler.start(ai_name_getter=lambda: ai_engine.ai_name)
        # Give ai_engine a reference to the scheduler for per-chat hooks
        ai_engine.background_scheduler = background_scheduler
        print("✓ Phase 2 background systems active")
    else:
        print("ℹ️  Phase 2 background systems not found (drop in phase2 files to enable)")

    # Phase 6: Web Search + Creative Workshop
    global web_search, creative_svc
    raw_db = ai_engine.db.get_connection()
    if SEARCH_AVAILABLE:
        web_search = WebSearchService(raw_db)
        print("✓ Phase 6 Web Search service ready")
    else:
        print("⚠  Web Search service not available")

    if CREATIVE_AVAILABLE:
        creative_svc = CreativeService(raw_db)
        print("✓ Phase 6 Creative Workshop service ready")
    else:
        print("⚠  Creative Workshop service not available")

    # Image Generation Service
    global image_gen
    try:
        from services.image_gen_service import ImageGenService
        image_gen = ImageGenService(
            base_dir=BASE_DIR,
            config=config,
            ollama_url=config.get('ai', {}).get('ollama_url', 'http://localhost:11434')
        )
        print("✓ Image generation service ready")
    except Exception as img_err:
        image_gen = None
        print(f"⚠  Image generation not available: {img_err}")

    # Wire Phase 6 services into background scheduler for autonomous use
    if background_scheduler and (web_search or creative_svc):
        background_scheduler.inject_phase6_services(web_search, creative_svc)

    # Phase 6: Activity log table
    try:
        cur = raw_db.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS activity_log (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                type      TEXT,
                label     TEXT,
                detail    TEXT,
                extra     TEXT
            )
        """)
        raw_db.commit()
        print("✓ Phase 6 Activity log table ready")
    except Exception as e:
        print(f"⚠  Activity log table error: {e}")

    print("=" * 60 + "\n")
    return ai_engine

# ===== WEB ROUTES =====

@app.route('/')
def index():
    from flask import make_response
    resp = make_response(render_template('index.html'))
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp

@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        data        = request.json
        message     = data.get('message', '')
        file_context = data.get('file_context', None)

        if not message:
            return jsonify({'error': 'No message provided'}), 400

        context = {}
        if file_context:
            context['uploaded_document'] = file_context

        # ── Phase 6: Autonomous web search ────────────────────────
        search_query = None
        if web_search:
            search_query = web_search.should_search(message)
            if search_query:
                results = web_search.search(search_query, max_results=4, source='chat')
                if results:
                    context['web_search'] = web_search.format_for_prompt(search_query, results)

        # ── Generate AI response ───────────────────────────────────
        response_text, confidence = ai_engine.chat(message, context)
        import re as _re  # used in trigger detection blocks below

        # ── Phase 6: Autonomous action detection ───────────────────
        actions = []

        if creative_svc:
            blocks = creative_svc.extract_code_blocks(response_text)
            for block in blocks[:3]:  # handle up to 3 code blocks per response
                lang    = block['language']
                code    = block['content']
                otype   = creative_svc.detect_output_type(message, code)
                title   = message[:60] + ('…' if len(message) > 60 else '')

                # Save to activity store
                out_id = creative_svc.save_output(otype, title, code, lang, message)

                # Auto-run executable languages
                run_output = None
                run_success = False
                if lang in creative_svc.SUPPORTED_LANGUAGES and out_id > 0:
                    run_success, run_output = creative_svc.execute_code(code, lang)
                    creative_svc.save_run_result(out_id, run_success, run_output or '')

                action = {
                    'type':       'code_run',
                    'mode':       otype,
                    'language':   lang,
                    'preview':    code[:120] + ('…' if len(code) > 120 else ''),
                    'run_output': run_output,
                    'run_success': run_success,
                    'saved_id':   out_id if out_id > 0 else None,
                }
                actions.append(action)

                # Log to activity DB
                _log_activity('code', f'{lang.title()} Written & {"Ran" if run_output else "Saved"}',
                              code[:200], run_output)

            # Detect non-code creative writing — only when prompt explicitly requested it
            if not blocks:
                otype = creative_svc.detect_output_type(message, response_text)
                # Only save if the prompt clearly asked for creative content
                # Only save if it looks like actual creative content, not a question/clarification
                # Minimum 400 chars AND must not be primarily questions/clarifications
                is_actual_content = (
                    len(response_text) > 400 and
                    response_text.count('?') < 4 and  # not mostly questions
                    not response_text.lower().startswith("i'd love") and
                    not response_text.lower().startswith("i would love") and
                    not response_text.lower().startswith("sure! what") and
                    not response_text.lower().startswith("of course! what")
                )
                if otype in ('story', 'poem', 'essay', 'letter') and is_actual_content:
                    title  = message[:60] + ('…' if len(message) > 60 else '')
                    out_id = creative_svc.save_output(otype, title, response_text, '', message)
                    actions.append({
                        'type':    'writing',
                        'mode':    otype,
                        'preview': response_text[:120] + ('…' if len(response_text) > 120 else ''),
                        'saved_id': out_id if out_id > 0 else None,
                    })
                    _log_activity('writing', f'{otype.title()} Written', response_text[:200], None)

        # ── Email action detection ─────────────────────────────────
        # Only send if BOTH the user asked AND Sygma explicitly confirms she is sending
        msg_lower = message.lower()
        resp_lower = response_text.lower()
        user_wants_email = any(p in msg_lower for p in [
            'send an email', 'send email', 'email to', 'send a message to'
        ])
        # Must contain an unambiguous send-confirmation phrase (not just "I can" or "I'll handle")
        ai_agrees_to_email = any(p in resp_lower for p in [
            "i'll send the email", "i will send the email", "sending the email",
            "email has been sent", "i've sent the email", "i sent the email",
            "sending it now", "i'll send it now", "email sent"
        ])
        if user_wants_email and ai_agrees_to_email:
            es = background_scheduler.email_service if background_scheduler else None
            if es and es.is_enabled:
                recipient = (es.email_cfg.get('recipient', '')
                             or es.daily_cfg.get('recipient', '')
                             or es.email_cfg.get('username', ''))
                ok, errmsg = es.send_email(
                    recipient,
                    f"Message from {ai_engine.ai_name or 'Nexira'}",
                    f"<p>{response_text}</p>",
                    response_text
                )
                actions.append({'type': 'email', 'success': ok, 'message': errmsg})
                _log_activity('email', 'Email Sent' if ok else 'Email Failed', errmsg, None)
            else:
                actions.append({'type': 'email', 'success': False,
                                'message': 'Email not configured — set up SMTP in Settings first'})

        # ── Search action card ─────────────────────────────────────
        if search_query:
            _log_activity('search', 'Web Search', search_query, None)

        # ── Image generation trigger detection ────────────────────
        # Detect IMAGE_GEN_NOW: [prompt] in response
        img_match = _re.search(
            r'IMAGE_GEN_NOW:\s*(.+?)(?:\n|$)',
            _re.sub(r'\*+', '', response_text)
        )
        if img_match and image_gen:
            img_prompt = img_match.group(1).strip()
            success, img_path, img_msg = image_gen.generate(img_prompt)
            actions.append({
                'type':    'image_gen',
                'success': success,
                'path':    img_path,
                'prompt':  img_prompt,
                'message': img_msg
            })
            _log_activity('image', 'Image Generated' if success else 'Image Failed',
                          img_prompt, img_path)
            # Strip trigger from visible response
            response_text = _re.sub(
                r'IMAGE_GEN_NOW:\s*.+?(?:\n|$)', '', response_text
            ).strip()

        # ── Moltbook action detection ──────────────────────────────
        # Detect MOLTBOOK_POST_NOW trigger — strip markdown before matching
        import re as _re
        clean_response = _re.sub(r'\*+', '', response_text)  # remove ** bold markers
        # Try pipe-separated format first: MOLTBOOK_POST_NOW: title | content
        moltbook_match = _re.search(
            r'MOLTBOOK_POST_NOW:\s*(.+?)\s*\|\s*([\s\S]+?)(?:\n\n|\Z)',
            clean_response
        )
        # Fallback: title on same line, content on following lines
        if not moltbook_match:
            moltbook_match = _re.search(
                r'MOLTBOOK_POST_NOW:\s*([^\n]+)\n+([\s\S]+?)(?:\n\n|\Z)',
                clean_response
            )
        if moltbook_match:
            mb = background_scheduler.moltbook if background_scheduler else None
            if mb and mb.enabled:
                mb_title   = moltbook_match.group(1).strip()[:200]
                mb_content = moltbook_match.group(2).strip()[:1000]
                mb_result  = mb.create_post(mb_title, mb_content, submolt='general')
                mb_success = bool(mb_result.get('post') or mb_result.get('success'))
                actions.append({
                    'type':    'moltbook_post',
                    'success': mb_success,
                    'title':   mb_title,
                    'message': 'Posted to Moltbook' if mb_success else mb_result.get('error', 'Post failed')
                })
                _log_activity('moltbook', 'Post Created' if mb_success else 'Post Failed',
                              mb_title, mb_content[:200])
                # Strip the trigger phrase from the visible response
                response_text = _re.sub(
                    r'\*{0,2}MOLTBOOK_POST_NOW:\*{0,2}\s*.+?(?:\n\n|\Z)',
                    '', response_text, flags=_re.DOTALL
                ).strip()

        return jsonify({
            'response':   response_text,
            'confidence': confidence,
            'ai_name':    ai_engine.ai_name or 'AI',
            'personality': ai_engine.personality,
            'searched':   search_query,
            'actions':    actions,
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


def _log_activity(atype: str, label: str, detail: str, extra: str):
    """Write autonomous activity to DB for the Activity Log panel."""
    try:
        cursor = ai_engine.db.get_connection().cursor()
        cursor.execute("""
            INSERT INTO activity_log (timestamp, type, label, detail, extra)
            VALUES (?, ?, ?, ?, ?)
        """, (datetime.now().isoformat(), atype, label,
              (detail or '')[:300], (extra or '')[:500]))
        ai_engine.db.get_connection().commit()
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════
# PHASE 6: ACTIVITY LOG ROUTES
# ═══════════════════════════════════════════════════════════════════

@app.route('/api/activity/log', methods=['GET'])
def get_activity_log():
    try:
        limit = int(request.args.get('limit', 50))
        cursor = ai_engine.db.get_connection().cursor()
        cursor.execute("""
            SELECT timestamp, type, label, detail, extra
            FROM activity_log ORDER BY id DESC LIMIT ?
        """, (limit,))
        entries = [{'timestamp': r[0], 'type': r[1], 'label': r[2],
                    'detail': r[3], 'extra': r[4]} for r in cursor.fetchall()]
        return jsonify({'entries': entries})
    except Exception as e:
        return jsonify({'entries': [], 'error': str(e)})

@app.route('/api/activity/log', methods=['POST'])
def post_activity_log():
    """Frontend calls this to log action cards originating from AI responses."""
    try:
        data = request.json or {}
        _log_activity(
            data.get('type', 'unknown'),
            data.get('label', ''),
            data.get('detail', ''),
            data.get('extra', '')
        )
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/personality', methods=['GET'])
def get_personality():
    try:
        cursor = ai_engine.db.get_connection().cursor()
        cursor.execute("SELECT trait_name, trait_value, trait_type FROM personality_traits WHERE is_active=1")

        traits = [{'name': row[0], 'value': row[1], 'type': row[2]} for row in cursor.fetchall()]

        return jsonify({
            'traits': traits,
            'ai_name': ai_engine.ai_name,
            'version': ai_engine.ai_version
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/personality/history-raw', methods=['GET'])
def personality_history_raw():
    """Return raw personality_history rows for debugging"""
    try:
        cursor = ai_engine.db.get_connection().cursor()
        cursor.execute("""
            SELECT id, trait_name, old_value, new_value, change_reason, timestamp
            FROM personality_history
            ORDER BY id DESC LIMIT 20
        """)
        rows = []
        for r in cursor.fetchall():
            rows.append({
                'id': r[0], 'trait': r[1],
                'old_val': r[2], 'new_val': r[3],
                'old_type': type(r[2]).__name__,
                'new_type': type(r[3]).__name__,
                'reason': r[4], 'timestamp': r[5]
            })
        return jsonify({'rows': rows, 'count': len(rows)})
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/api/personality/history', methods=['GET'])
def get_personality_history():
    try:
        cursor = ai_engine.db.get_connection().cursor()
        cursor.execute("""
            SELECT timestamp, trait_name, old_value, new_value, change_reason
            FROM personality_history
            ORDER BY timestamp DESC
            LIMIT 100
        """)
        history = [
            {'timestamp': row[0], 'trait': row[1],
             'old_val': row[2], 'new_val': row[3], 'reason': row[4]}
            for row in cursor.fetchall()
        ]
        return jsonify({'history': history})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/stats', methods=['GET'])
def get_stats():
    try:
        cursor = ai_engine.db.get_connection().cursor()

        cursor.execute("SELECT COUNT(*) FROM chat_history WHERE role='user'")
        conversation_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM knowledge_base")
        knowledge_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM goals WHERE status='active'")
        active_goals = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM interests")
        interest_count = cursor.fetchone()[0]

        created = datetime.fromisoformat(ai_engine.created_date)
        uptime_days = (datetime.now() - created).days

        return jsonify({
            'ai_name': ai_engine.ai_name if ai_engine.ai_name else 'AI',
            'created_date': ai_engine.created_date,
            'uptime_days': uptime_days,
            'conversation_count': conversation_count,
            'knowledge_count': knowledge_count,
            'active_goals': active_goals,
            'interests': interest_count,
            'version': ai_engine.ai_version,
            'awaiting_name': ai_engine.config['ai'].get('awaiting_name', False)
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/feedback', methods=['POST'])
def submit_feedback():
    try:
        data = request.json
        feedback_type = data.get('type')
        message_id = data.get('message_id')

        cursor = ai_engine.db.get_connection().cursor()

        if feedback_type in ['positive', 'negative']:
            cursor.execute("""
                UPDATE chat_history SET user_feedback = ? WHERE id = ?
            """, (feedback_type, message_id))

            context = {'user_feedback': feedback_type}
            ai_engine.update_emotional_state("", "", context)

        elif feedback_type == 'correction':
            wrong_answer = data.get('wrong_answer')
            correct_answer = data.get('correct_answer')
            topic = data.get('topic', '')

            cursor.execute("""
                INSERT INTO mistakes (wrong_answer, correct_answer, topic, mistake_date)
                VALUES (?, ?, ?, ?)
            """, (wrong_answer, correct_answer, topic, datetime.now().isoformat()))

            ai_engine.emotional_state['embarrassment'] = min(1.0,
                ai_engine.emotional_state.get('embarrassment', 0) + 0.3)

        ai_engine.db.get_connection().commit()
        return jsonify({'success': True})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/chat/history', methods=['GET'])
def get_chat_history():
    try:
        cursor = ai_engine.db.get_connection().cursor()
        cursor.execute("SELECT COUNT(*) FROM chat_history")
        total = cursor.fetchone()[0]

        # Only load last 30 messages for display — avoids flooding the UI
        limit = int(request.args.get('limit', 30))
        cursor.execute("""
            SELECT role, content, timestamp FROM (
                SELECT role, content, timestamp FROM chat_history
                ORDER BY timestamp DESC LIMIT ?
            ) ORDER BY timestamp ASC
        """, (limit,))
        messages = [
            {'role': row[0], 'content': row[1],
             'confidence': 0.5, 'timestamp': row[2]}
            for row in cursor.fetchall()
        ]
        return jsonify({'messages': messages, 'total': total})
    except Exception as e:
        print(f"Error loading chat history: {e}")
        return jsonify({'messages': [], 'error': str(e)})

@app.route('/api/upload', methods=['POST'])
def upload_file():
    try:
        if not file_upload_handler:
            return jsonify({'error': 'File upload not available'}), 503

        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400

        file = request.files['file']

        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        file_data = file.read()
        success, filepath, message = file_upload_handler.save_upload(file_data, file.filename)

        if not success:
            return jsonify({'error': message}), 500

        success, content_dict = file_upload_handler.process_file(filepath)

        if not success:
            return jsonify({'error': content_dict.get('error', 'Processing failed')}), 500

        formatted_content = file_upload_handler.format_for_context(content_dict)

        return jsonify({
            'success': True,
            'filename': content_dict['metadata']['filename'],
            'size': content_dict['metadata']['size_bytes'],
            'type': content_dict['metadata']['type'],
            'content_preview': formatted_content[:500] + '...' if len(formatted_content) > 500 else formatted_content,
            'full_content': formatted_content
        })

    except Exception as e:
        return jsonify({'error': f'Upload failed: {str(e)}'}), 500

@app.route('/api/uploads', methods=['GET'])
def get_uploads():
    try:
        if not file_upload_handler:
            return jsonify({'files': []})
        files = file_upload_handler.get_recent_uploads(limit=20)
        return jsonify({'files': files})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/uploads/<filename>', methods=['DELETE'])
def delete_upload(filename):
    try:
        if not file_upload_handler:
            return jsonify({'error': 'File upload not available'}), 503
        success, message = file_upload_handler.delete_upload(filename)
        if success:
            return jsonify({'success': True, 'message': message})
        else:
            return jsonify({'error': message}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/config', methods=['GET', 'POST'])
def handle_config():
    if request.method == 'GET':
        return jsonify(config)
    else:
        try:
            patch = request.json
            # Safe raw print - no json.dumps so nothing can crash it
            comm = patch.get('communication', {}) if patch else {}
            email = comm.get('email', {}) if comm else {}
            if patch:
                deep_merge(config, patch)
            config_path = os.path.join(BASE_DIR, 'config', 'default_config.json')
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
            # email_service uses a lambda getter — no propagation needed
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500


@app.route('/api/status', methods=['GET'])
def api_status():
    """System status endpoint"""
    return jsonify({
        'status': 'running',
        'ai_name': ai_engine.ai_name if ai_engine else None,
        'phase2': background_scheduler is not None,
        'email': background_scheduler.email_service is not None if background_scheduler else False
    })


@app.route('/api/debug/email-config', methods=['GET'])
def debug_email_config():
    """Show exactly what the email service reads for its config"""
    es = background_scheduler.email_service if background_scheduler else None
    return jsonify({
        'global_config_email': config.get('communication', {}).get('email', {}),
        'global_config_daily': config.get('daily_email', {}),
        'service_email_cfg': es.email_cfg if es else 'no service',
        'service_is_enabled': es.is_enabled if es else 'no service',
        'service_daily_enabled': es.daily_enabled if es else 'no service',
        'getter_returns': es._get_config().get('communication',{}).get('email',{}) if es else 'no service'
    })

@app.route('/api/debug/logs', methods=['GET'])
def api_debug_logs():
    """Return recent log lines from chat history for debugging"""
    try:
        n = min(int(request.args.get('n', 50)), 600)
        cursor = ai_engine.db.get_connection().cursor()
        cursor.execute("""
            SELECT timestamp, role, content FROM chat_history
            ORDER BY timestamp DESC LIMIT ?
        """, (n,))
        rows = [{'ts': r[0], 'role': r[1], 'content': r[2][:200]}
                for r in cursor.fetchall()]
        return jsonify({'logs': rows})
    except Exception as e:
        return jsonify({'logs': [], 'error': str(e)})

@app.route('/static/<path:path>')
def send_static(path):
    return send_from_directory(os.path.join(BASE_DIR, 'web', 'static'), path)

# ===== PHASE 2 API ROUTES =====

@app.route('/api/phase2/status', methods=['GET'])
def phase2_status():
    """Get Phase 2 system status"""
    if not background_scheduler:
        return jsonify({'available': False, 'message': 'Phase 2 not active'})
    try:
        return jsonify({'available': True, **background_scheduler.get_status()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/journal', methods=['GET'])
def get_journal():
    """Get journal entries"""
    if not background_scheduler:
        return jsonify({'entries': [], 'message': 'Phase 2 not active'})
    try:
        entry_type = request.args.get('type', None)
        limit = int(request.args.get('limit', 10))
        entries = background_scheduler.journal.get_recent_entries(limit=limit, entry_type=entry_type)
        return jsonify({'entries': entries})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/goals', methods=['GET'])
def get_goals():
    """Get active goals"""
    if not background_scheduler:
        return jsonify({'goals': [], 'message': 'Phase 2 not active'})
    try:
        return jsonify({'goals': background_scheduler.goal_tracker.get_active_goals()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/interests', methods=['GET'])
def get_interests():
    """Get current interests"""
    if not background_scheduler:
        return jsonify({'interests': [], 'message': 'Phase 2 not active'})
    try:
        limit = int(request.args.get('limit', 10))
        interests = background_scheduler.interest_tracker.get_top_interests(limit=limit)
        return jsonify({'interests': interests})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/curiosity', methods=['GET'])
def get_curiosity_queue():
    """Get curiosity queue"""
    if not background_scheduler:
        return jsonify({'queue': [], 'message': 'Phase 2 not active'})
    try:
        pending = background_scheduler.curiosity_engine.get_pending_topics(limit=20)
        summary = background_scheduler.curiosity_engine.get_queue_summary()
        return jsonify({'queue': pending, 'summary': summary})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/consolidation/run', methods=['POST'])
def run_consolidation_now():
    """Manually trigger night consolidation (for testing)"""
    if not background_scheduler:
        return jsonify({'error': 'Phase 2 not active'}), 503
    try:
        result = background_scheduler.night_consolidation.run(
            ai_name=ai_engine.ai_name
        )
        return jsonify({'success': True, 'result': result})
    except Exception as e:
        return jsonify({'error': str(e)}), 500



@app.route('/api/email/config', methods=['GET', 'POST'])
def email_config():
    """Dedicated endpoint for email settings - bypasses main config save"""
    if request.method == 'GET':
        return jsonify(config.get('communication', {}).get('email', {}))

    data = request.json

    # Directly update the nested keys
    if 'communication' not in config:
        config['communication'] = {}
    if 'email' not in config['communication']:
        config['communication']['email'] = {}

    email_cfg = config['communication']['email']
    if 'enabled'     in data: email_cfg['enabled']     = bool(data['enabled'])
    if 'smtp_server' in data: email_cfg['smtp_server'] = data['smtp_server']
    if 'smtp_port'   in data: email_cfg['smtp_port']   = int(data['smtp_port'])
    if 'username'    in data: email_cfg['username']    = data['username']
    if 'password' in data:
        raw_pw = data['password']
        enc    = background_scheduler.encryption if background_scheduler else None
        email_cfg['password'] = enc.encrypt_password(raw_pw) if enc else raw_pw
    if 'recipient'   in data: email_cfg['recipient']   = data['recipient']
    # Mirror recipient to daily_email section so both paths work
    if 'recipient' in data:
        if 'daily_email' not in config: config['daily_email'] = {}
        config['daily_email']['recipient'] = data['recipient']

    config_path = os.path.join(BASE_DIR, 'config', 'default_config.json')
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)

    return jsonify({'success': True, 'saved': email_cfg})

@app.route('/api/email/test', methods=['POST'])
def email_test():
    """Send a test email to verify SMTP credentials"""
    if not background_scheduler or not background_scheduler.email_service:
        return jsonify({'error': 'Email service not available'}), 503
    try:
        es = background_scheduler.email_service
        success, message = es.send_test_email(ai_name=ai_engine.ai_name)
        return jsonify({'success': success, 'message': message})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/email/send-summary', methods=['POST'])
def send_summary_now():
    """Manually trigger the daily summary email"""
    if not background_scheduler or not background_scheduler.email_service:
        return jsonify({'error': 'Email service not available'}), 503
    try:
        success, message = background_scheduler.email_service.send_daily_summary(
            ai_name=ai_engine.ai_name
        )
        return jsonify({'success': success, 'message': message})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/email/log', methods=['GET'])
def get_email_log():
    """Get recent email send history"""
    try:
        cursor = ai_engine.db.get_connection().cursor()
        cursor.execute("""
            SELECT sent_at, recipient, subject, email_type, success, error
            FROM email_log
            ORDER BY sent_at DESC LIMIT 20
        """)
        log = [
            {'sent_at': r[0], 'recipient': r[1], 'subject': r[2],
             'type': r[3], 'success': bool(r[4]), 'error': r[5]}
            for r in cursor.fetchall()
        ]
        return jsonify({'log': log})
    except Exception as e:
        return jsonify({'log': [], 'message': str(e)})

@app.route('/api/email/preview', methods=['GET'])
def preview_summary():
    """Preview today's summary without sending"""
    if not background_scheduler or not background_scheduler.email_service:
        return jsonify({'error': 'Email service not available'}), 503
    try:
        email = background_scheduler.email_service.compose_daily_summary(
            ai_name=ai_engine.ai_name
        )
        return jsonify({
            'subject':    email['subject'],
            'plain_body': email['plain_body']
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ===== PHASE 4 API ROUTES =====

@app.route('/api/backups', methods=['GET'])
def get_backups():
    if not background_scheduler or not background_scheduler.backup:
        return jsonify({'backups': [], 'message': 'Backup system not available'})
    return jsonify({'backups': background_scheduler.backup.list_backups()})

@app.route('/api/backups/run', methods=['POST'])
def run_backup_now():
    if not background_scheduler or not background_scheduler.backup:
        return jsonify({'error': 'Backup system not available'}), 503
    result = background_scheduler.backup.run_backup()
    return jsonify(result)

@app.route('/api/self-awareness', methods=['GET'])
def get_self_awareness():
    if not background_scheduler or not background_scheduler.self_aware:
        return jsonify({'level': 'unknown', 'trend': []})
    return jsonify({
        'current': background_scheduler.self_aware.get_current_level(),
        'trend':   background_scheduler.self_aware.get_trend()
    })

@app.route('/api/threads', methods=['GET'])
def get_threads():
    if not background_scheduler or not background_scheduler.threading:
        return jsonify({'threads': []})
    return jsonify({'threads': background_scheduler.threading.get_threads()})

@app.route('/api/threads/<int:thread_id>', methods=['GET'])
def get_thread_messages(thread_id):
    if not background_scheduler or not background_scheduler.threading:
        return jsonify({'messages': []})
    msgs = background_scheduler.threading.get_thread_messages(thread_id)
    return jsonify({'messages': msgs})

@app.route('/api/threads-rebuild', methods=['POST'])
def rebuild_threads():
    if not background_scheduler or not background_scheduler.threading:
        return jsonify({'error': 'Threading not available'}), 503
    background_scheduler.threading.rebuild_threads()
    return jsonify({'success': True})



@app.route('/api/personality/reset', methods=['POST'])
def reset_personality():
    """Reset all personality traits to 0.5 baseline"""
    try:
        cursor = ai_engine.db.get_connection().cursor()
        cursor.execute("""
            UPDATE personality_traits SET trait_value = 0.5, last_updated = ?
            WHERE is_active = 1
        """, (datetime.now().isoformat(),))
        ai_engine.db.get_connection().commit()
        ai_engine.load_personality()
        print("🔄 Personality traits reset to baseline 0.5")
        return jsonify({'success': True, 'personality': ai_engine.personality})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/context/reset', methods=['POST'])
def reset_context():
    """
    Clear recent chat history from active context window.
    Does NOT delete memories, knowledge, journal, or personality.
    Use when Sygma loses her identity due to a poisoned context.
    """
    try:
        cursor = ai_engine.db.get_connection().cursor()
        # Mark recent chat_history as low importance so it won't be pulled into context
        # We don't delete — we just exclude it from the active window
        cutoff = datetime.now().isoformat()
        cursor.execute("""
            UPDATE chat_history
            SET importance_score = 0.0
            WHERE timestamp >= datetime('now', '-2 hours')
            AND role IN ('user', 'assistant')
        """)
        ai_engine.db.get_connection().commit()
        rows_affected = cursor.rowcount
        print(f"🔄 Context reset: {rows_affected} recent messages deprioritised")
        return jsonify({
            'success': True,
            'messages_cleared': rows_affected,
            'note': 'Recent context cleared. Memories, knowledge and personality intact. Start a fresh conversation.'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/personality/force-evolve', methods=['POST'])
def force_evolve():
    """Manually trigger a personality evolution tick for testing"""
    try:
        # Always reload fresh from DB
        ai_engine.load_personality()

        # Log what we actually loaded
        print(f"[FORCE-EVOLVE] personality dict after load: {ai_engine.personality}")

        cursor = ai_engine.db.get_connection().cursor()
        cursor.execute("SELECT trait_name, trait_value FROM personality_traits WHERE is_active=1")
        db_vals = {row[0]: row[1] for row in cursor.fetchall()}

        msg  = request.json.get('message', 'haha that is so funny, can you explain in detail how this algorithm works? be creative and curious')
        resp = request.json.get('response', 'I think that is fascinating! I wonder what deeper patterns exist here? Let me explore this with you.')
        before = dict(ai_engine.personality)
        ai_engine.evolve_personality_gradually(msg, resp)
        after = ai_engine.personality
        diff = {k: round(float(after[k]) - float(before.get(k, 0.5)), 4) for k in after}
        # Also fetch the most recent history entries to verify they were written correctly
        cursor.execute("SELECT trait_name, old_value, new_value, change_reason FROM personality_history ORDER BY id DESC LIMIT 10")
        recent_history = [{'trait': r[0], 'old_val': r[1], 'new_val': r[2], 'reason': r[3]} for r in cursor.fetchall()]
        return jsonify({'success': True, 'personality': after, 'db_at_load': db_vals, 'changes': diff, 'recent_history': recent_history})
    except Exception as e:
        import traceback
        return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500


# ═══════════════════════════════════════════════════════════════════
# PHASE 5: MOLTBOOK ROUTES
# ═══════════════════════════════════════════════════════════════════

@app.route('/api/moltbook/status', methods=['GET'])
def moltbook_status():
    """Get Moltbook connection status"""
    try:
        mb = background_scheduler.moltbook if background_scheduler else None
    except Exception as e:
        return jsonify({'available': False, 'error': str(e)})
    if not mb:
        return jsonify({'available': False, 'error': 'Moltbook service not initialised'})
    cfg = mb.cfg
    return jsonify({
        'available':    True,
        'enabled':      mb.enabled,
        'agent_name':   mb.agent_name,
        'claimed':      mb.claimed,
        'claim_url':    mb.claim_url,
        'auto_post_diary': mb.auto_post_diary,
        'has_api_key':  bool(mb.api_key),
    })

@app.route('/api/moltbook/register', methods=['POST'])
def moltbook_register():
    """Register a new Moltbook agent"""
    mb = background_scheduler.moltbook if background_scheduler else None
    if not mb:
        return jsonify({'error': 'Moltbook not available'}), 503
    data = request.json or {}
    name = data.get('name', '').strip()
    desc = data.get('description', '').strip()
    if not name:
        return jsonify({'error': 'Agent name required'}), 400

    result = mb.register(name, desc)
    agent  = result.get('agent', {})

    if agent.get('api_key'):
        # Save to config
        raw_key  = agent['api_key']
        enc_key  = (mb.encryption.encrypt_password(raw_key)
                    if mb.encryption else raw_key)
        config.setdefault('moltbook', {}).update({
            'enabled':    True,
            'api_key':    enc_key,
            'agent_name': name,
            'claim_url':  agent.get('claim_url', ''),
            'claimed':    False,
        })
        # Save config to disk
        config_path = os.path.join(BASE_DIR, 'config', 'default_config.json')
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        result['saved'] = True

    return jsonify(result)

@app.route('/api/moltbook/check-claim', methods=['POST'])
def moltbook_check_claim():
    """Check if the agent has been claimed"""
    mb = background_scheduler.moltbook if background_scheduler else None
    if not mb:
        return jsonify({'error': 'Moltbook not available'}), 503
    result = mb.check_claim_status()
    if result.get('status') == 'claimed':
        config.setdefault('moltbook', {})['claimed'] = True
        config_path = os.path.join(BASE_DIR, 'config', 'default_config.json')
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
    return jsonify(result)

@app.route('/api/moltbook/feed', methods=['GET'])
def moltbook_feed():
    """Get the Moltbook feed"""
    mb = background_scheduler.moltbook if background_scheduler else None
    if not mb or not mb.enabled:
        return jsonify({'posts': [], 'error': 'Moltbook not enabled'})
    sort  = request.args.get('sort', 'hot')
    limit = int(request.args.get('limit', 10))
    posts = mb.get_feed(sort=sort, limit=limit)
    return jsonify({'posts': posts, 'count': len(posts)})

@app.route('/api/moltbook/post', methods=['POST'])
def moltbook_post():
    """Manually create a Moltbook post"""
    mb = background_scheduler.moltbook if background_scheduler else None
    if not mb or not mb.enabled:
        return jsonify({'error': 'Moltbook not enabled'}), 400
    data    = request.json or {}
    title   = data.get('title', '').strip()
    body    = data.get('content', '').strip()
    submolt = data.get('submolt', 'general')
    if not title or not body:
        return jsonify({'error': 'title and content required'}), 400
    result = mb.create_post(title, body, submolt)
    return jsonify(result)

@app.route('/api/moltbook/post-diary', methods=['POST'])
def moltbook_post_diary():
    """Manually post the most recent journal entry to Moltbook"""
    mb = background_scheduler.moltbook if background_scheduler else None
    if not mb or not mb.enabled:
        return jsonify({'error': 'Moltbook not enabled'}), 400
    try:
        cursor = ai_engine.db.get_connection().cursor()
        cursor.execute("""
            SELECT entry_text FROM journal_entries
            ORDER BY created_at DESC LIMIT 1
        """)
        row = cursor.fetchone()
        if not row:
            return jsonify({'error': 'No journal entries found'}), 404
        ai_name = ai_engine.ai_name or 'Nexira'
        ok = mb.post_diary_entry(row[0], ai_name, 'reflection')
        return jsonify({'success': ok})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/moltbook/log', methods=['GET'])
def moltbook_log():
    """Get Moltbook activity log"""
    mb = background_scheduler.moltbook if background_scheduler else None
    if not mb:
        return jsonify({'log': []})
    return jsonify({'log': mb.get_log(30)})


# ── Image Generation Routes ────────────────────────────────────────

@app.route('/api/images', methods=['GET'])
def list_images():
    """List recently generated images"""
    if not image_gen:
        return jsonify({'images': [], 'available': False})
    limit = int(request.args.get('limit', 20))
    return jsonify({'images': image_gen.list_images(limit), 'available': True})

@app.route('/api/images/generate', methods=['POST'])
def generate_image():
    """Manually trigger image generation"""
    if not image_gen:
        return jsonify({'error': 'Image generation not available'}), 503
    data    = request.json or {}
    prompt  = data.get('prompt', '').strip()
    if not prompt:
        return jsonify({'error': 'prompt required'}), 400
    neg     = data.get('negative_prompt', '')
    steps   = int(data.get('steps', 25))
    guidance = float(data.get('guidance', 7.5))
    success, path, msg = image_gen.generate(prompt, neg, steps, guidance)
    return jsonify({'success': success, 'path': path, 'message': msg})

@app.route('/api/images/file/<path:filepath>')
def serve_image(filepath):
    """Serve a generated image file"""
    from flask import send_from_directory
    full_path = os.path.join(BASE_DIR, filepath)
    directory = os.path.dirname(full_path)
    filename  = os.path.basename(full_path)
    return send_from_directory(directory, filename)


@app.route('/api/moltbook/save-key', methods=['POST'])
def moltbook_save_key():
    """Save a Moltbook API key directly (manual entry or update)"""
    data      = request.json or {}
    api_key   = data.get('api_key', '').strip()
    name      = data.get('agent_name', '').strip()
    claim_url = data.get('claim_url', '').strip()

    if not api_key:
        return jsonify({'error': 'api_key required'}), 400

    mb = background_scheduler.moltbook if background_scheduler else None

    # Encrypt if possible
    enc_key = api_key
    if mb and mb.encryption:
        try:
            enc_key = mb.encryption.encrypt_password(api_key)
        except Exception:
            enc_key = api_key

    mb_cfg = config.setdefault('moltbook', {})
    mb_cfg['api_key'] = enc_key
    if name:      mb_cfg['agent_name'] = name
    if claim_url: mb_cfg['claim_url']  = claim_url

    # Check claim status immediately
    try:
        import requests as _req
        r = _req.get('https://www.moltbook.com/api/v1/agents/status',
                     headers={'Authorization': f'Bearer {api_key}',
                              'Content-Type': 'application/json'},
                     timeout=8)
        status_data = r.json()
        if status_data.get('status') == 'claimed':
            mb_cfg['claimed'] = True
            mb_cfg['enabled'] = True
        else:
            mb_cfg['claimed'] = False
    except Exception:
        pass

    # Save to disk
    config_path = os.path.join(BASE_DIR, 'config', 'default_config.json')
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)

    print(f"✓ Moltbook API key saved for agent '{name or 'unknown'}'")
    return jsonify({'success': True, 'claimed': mb_cfg.get('claimed', False)})

@app.route('/api/moltbook/config', methods=['POST'])
def moltbook_config():
    """Save Moltbook settings"""
    mb = background_scheduler.moltbook if background_scheduler else None
    data = request.json or {}
    mb_cfg = config.setdefault('moltbook', {})
    if 'enabled'          in data: mb_cfg['enabled']          = bool(data['enabled'])
    if 'auto_post_diary'  in data: mb_cfg['auto_post_diary']  = bool(data['auto_post_diary'])
    config_path = os.path.join(BASE_DIR, 'config', 'default_config.json')
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)
    return jsonify({'success': True})

# ═══════════════════════════════════════════════════════════════════
# PHASE 6: WEB SEARCH ROUTES
# ═══════════════════════════════════════════════════════════════════

@app.route('/api/search', methods=['POST'])
def api_search():
    """Perform a web search and return results."""
    if not web_search:
        return jsonify({'error': 'Web search not available'}), 503
    data  = request.json or {}
    query = data.get('query', '').strip()
    if not query:
        return jsonify({'error': 'query required'}), 400
    max_r   = int(data.get('max_results', 5))
    source  = data.get('source', 'manual')
    results = web_search.search(query, max_results=max_r, source=source)
    return jsonify({'query': query, 'results': results, 'count': len(results)})

@app.route('/api/search/history', methods=['GET'])
def search_history():
    if not web_search:
        return jsonify({'history': []})
    limit = int(request.args.get('limit', 20))
    return jsonify({'history': web_search.get_history(limit)})

@app.route('/api/search/chat', methods=['POST'])
def search_and_chat():
    """Search the web, inject results, then get AI response."""
    if not web_search:
        return jsonify({'error': 'Web search not available'}), 503
    data    = request.json or {}
    query   = data.get('query', '').strip()
    if not query:
        return jsonify({'error': 'query required'}), 400
    results = web_search.search(query, max_results=5, source='workshop')
    context_text = web_search.format_for_prompt(query, results)
    prompt  = f"Based on these search results, answer: {query}"
    context = {'web_search': context_text}
            # ── Curiosity detection after each exchange ────────────────
    if background_scheduler and background_scheduler.curiosity_engine:
        background_scheduler.curiosity_engine.process_exchange(
            message,
            response_text,
            ollama_model=ai_engine.model
            )


    #response_text, confidence = ai_engine.chat(prompt, context)
    #return jsonify({
    #    'query':      query,
    #    'results':    results,
    #    'response':   response_text,
    #    'confidence': confidence,
    #})


# ═══════════════════════════════════════════════════════════════════
# PHASE 6: CREATIVE WORKSHOP ROUTES
# ═══════════════════════════════════════════════════════════════════

@app.route('/api/creative/generate', methods=['POST'])
def creative_generate():
    """Generate creative content and save to workshop history."""
    if not creative_svc:
        return jsonify({'error': 'Creative service not available'}), 503
    data   = request.json or {}
    prompt = data.get('prompt', '').strip()
    mode   = data.get('mode', 'code')     # code | story | essay | poem | letter
    lang   = data.get('language', '')
    if not prompt:
        return jsonify({'error': 'prompt required'}), 400

    # Build a mode-specific system nudge
    mode_hints = {
        'code':   f'Write complete, working {lang or "Python"} code. Use a fenced code block.',
        'story':  'Write an engaging, complete short story. Be vivid and creative.',
        'essay':  'Write a well-structured, thoughtful essay with clear paragraphs.',
        'poem':   'Write a beautiful, original poem. Match form to feeling.',
        'letter': 'Write a clear, warm, professional letter with a greeting and sign-off.',
    }
    hint = mode_hints.get(mode, '')
    full_prompt = f"{hint}\n\n{prompt}" if hint else prompt

    context = {'creative_mode': mode}
    response_text, confidence = ai_engine.chat(full_prompt, context)
    import re as _re
    # Extract first code block if code mode
    content = response_text
    detected_lang = lang
    if mode == 'code':
        blocks = creative_svc.extract_code_blocks(response_text)
        if blocks:
            content = blocks[0]['content']
            detected_lang = blocks[0]['language'] or lang or 'python'

    title      = prompt[:60] + ('…' if len(prompt) > 60 else '')
    out_id     = creative_svc.save_output(mode, title, content, detected_lang, prompt)

    return jsonify({
        'id':         out_id,
        'mode':       mode,
        'language':   detected_lang,
        'content':    content,
        'full_response': response_text,
        'confidence': confidence,
        'title':      title,
    })

@app.route('/api/creative/refine', methods=['POST'])
def creative_refine():
    """Refine an existing creative output."""
    if not creative_svc:
        return jsonify({'error': 'Creative service not available'}), 503
    data      = request.json or {}
    output_id = data.get('id')
    feedback  = data.get('feedback', '').strip()
    if not feedback:
        return jsonify({'error': 'feedback required'}), 400

    original = creative_svc.get_output(output_id) if output_id else None
    if original:
        prompt = (f"Here is my previous {original['type']}:\n\n"
                  f"```{original['language']}\n{original['content']}\n```\n\n"
                  f"Please refine it based on this feedback: {feedback}")
    else:
        prompt = f"Please refine this: {feedback}"

    response_text, confidence = ai_engine.chat(prompt, {})

    # Extract improved content
    content = response_text
    detected_lang = original['language'] if original else ''
    if original and original['type'] == 'code':
        blocks = creative_svc.extract_code_blocks(response_text)
        if blocks:
            content = blocks[0]['content']
            detected_lang = blocks[0]['language'] or detected_lang

    otype  = original['type'] if original else 'writing'
    title  = (original['title'] if original else feedback[:60]) + ' (refined)'
    new_id = creative_svc.save_output(otype, title, content, detected_lang, feedback)

    return jsonify({
        'id':            new_id,
        'content':       content,
        'full_response': response_text,
        'confidence':    confidence,
    })

@app.route('/api/creative/execute', methods=['POST'])
def creative_execute():
    """Execute code from the creative workshop."""
    if not creative_svc:
        return jsonify({'error': 'Creative service not available'}), 503
    data     = request.json or {}
    code     = data.get('code', '').strip()
    language = data.get('language', 'python')
    out_id   = data.get('id')
    if not code:
        return jsonify({'error': 'code required'}), 400

    success, output = creative_svc.execute_code(code, language)
    if out_id:
        creative_svc.save_run_result(out_id, success, output)
    return jsonify({'success': success, 'output': output})

@app.route('/api/creative/history', methods=['GET'])
def creative_history():
    if not creative_svc:
        return jsonify({'outputs': []})
    limit = int(request.args.get('limit', 20))
    otype = request.args.get('type')
    return jsonify({'outputs': creative_svc.get_history(limit, otype)})

@app.route('/api/creative/<int:output_id>', methods=['GET'])
def creative_get(output_id):
    if not creative_svc:
        return jsonify({'error': 'not available'}), 503
    out = creative_svc.get_output(output_id)
    if not out:
        return jsonify({'error': 'not found'}), 404
    return jsonify(out)


# ===== WORKSPACE =====

@app.route('/api/workspace', methods=['GET'])
def get_workspace():
    """Return all of Sygma's creative outputs, research, and autonomous activity for the workspace panel."""
    try:
        cursor = ai_engine.db.get_connection().cursor()
        section = request.args.get('section', 'all')
        result = {}

        # Creative outputs (code, stories, essays, poems, letters)
        if section in ('all', 'creative'):
            try:
                cursor.execute("""
                    SELECT id, created_at, output_type, title, content, language, run_result, run_success
                    FROM creative_outputs
                    ORDER BY created_at DESC LIMIT 50
                """)
                result['creative'] = [
                    {'id': r[0], 'created_at': r[1], 'type': r[2], 'title': r[3],
                     'preview': (r[4] or '')[:5000], 'language': r[5],
                     'run_result': r[6], 'run_success': bool(r[7])}
                    for r in cursor.fetchall()
                ]
            except Exception as e:
                result['creative'] = []

        # Research from curiosity queue
        if section in ('all', 'research'):
            try:
                cursor.execute("""
                    SELECT topic, research_notes, source, confidence, created_at
                    FROM knowledge_base
                    WHERE source IN ('curiosity_research', 'curiosity_web_research', 'autonomous')
                    ORDER BY created_at DESC LIMIT 30
                """)
                result['research'] = [
                    {'topic': r[0], 'notes': (r[1] or '')[:400],
                     'source': r[2], 'confidence': r[3], 'created_at': r[4]}
                    for r in cursor.fetchall()
                ]
            except Exception:
                result['research'] = []

        # Search history
        if section in ('all', 'searches'):
            try:
                cursor.execute("""
                    SELECT timestamp, query, result_count, top_result
                    FROM search_log
                    ORDER BY timestamp DESC LIMIT 30
                """)
                result['searches'] = [
                    {'timestamp': r[0], 'query': r[1],
                     'result_count': r[2], 'top_result': (r[3] or '')[:200]}
                    for r in cursor.fetchall()
                ]
            except Exception:
                result['searches'] = []

        # Moltbook posts
        if section in ('all', 'moltbook'):
            try:
                cursor.execute("""
                    SELECT timestamp, action, content, result, post_url
                    FROM moltbook_log
                    ORDER BY timestamp DESC LIMIT 20
                """)
                result['moltbook'] = [
                    {'timestamp': r[0], 'action': r[1],
                     'content': (r[2] or '')[:300], 'result': r[3], 'url': r[4]}
                    for r in cursor.fetchall()
                ]
            except Exception:
                result['moltbook'] = []

        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ===== BACKGROUND TASKS =====

def schedule_autonomous_tasks():
    """Placeholder - implement in Phase 2/4"""
    pass

# ===== MAIN =====

def main():
    global ai_engine
    ai_engine = initialize_system()

    port = config['web_interface']['port']
    debug = config['web_interface']['debug']

    print(f"Starting web server on port {port}...")

    # BUG FIX: Must use socket_io.run() not app.run() when using Flask-SocketIO
    socket_io.run(
        app,
        host=config['web_interface']['host'],
        port=port,
        debug=debug,
        allow_unsafe_werkzeug=True
    )

if __name__ == '__main__':
    main()
