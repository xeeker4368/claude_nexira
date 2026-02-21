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

# Initialize Flask app
app = Flask(__name__,
            template_folder=os.path.join(BASE_DIR, 'web', 'templates'),
            static_folder=os.path.join(BASE_DIR, 'web', 'static'))
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

    print("="*60 + "\n")
    return ai_engine

# ===== WEB ROUTES =====

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        message = data.get('message', '')
        file_context = data.get('file_context', None)

        if not message:
            return jsonify({'error': 'No message provided'}), 400

        context = {}
        if file_context:
            context['uploaded_document'] = file_context

        response, confidence = ai_engine.chat(message, context)

        return jsonify({
            'response': response,
            'confidence': confidence,
            'ai_name': ai_engine.ai_name if ai_engine.ai_name else 'AI',
            'timestamp': datetime.now().isoformat()
        })

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
                'old_raw': r[2], 'new_raw': r[3],
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
            {'timestamp': row[0], 'trait': row[1], 'old_value': row[2],
             'new_value': row[3], 'reason': row[4]}
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
        cursor.execute("""
            SELECT role, content
            FROM chat_history
            ORDER BY timestamp ASC
            LIMIT 100
        """)

        messages = [
            {'role': row[0], 'content': row[1], 'confidence': 0.5}
            for row in cursor.fetchall()
        ]

        return jsonify({'messages': messages})

    except Exception as e:
        print(f"Error loading chat history: {e}")
        return jsonify({'messages': []})

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
            print(f"[CONFIG SAVE] RAW PATCH KEYS: {list(patch.keys()) if patch else 'EMPTY/None'}")
            comm = patch.get('communication', {}) if patch else {}
            email = comm.get('email', {}) if comm else {}
            email_safe = {k: ('***' if k == 'password' else v) for k, v in email.items()}
            print(f"[CONFIG SAVE] patch.communication.email = {email_safe}")
            print(f"[CONFIG SAVE] config BEFORE: email enabled={config.get('communication',{}).get('email',{}).get('enabled')}")
            if patch:
                deep_merge(config, patch)
            print(f"[CONFIG SAVE] config AFTER:  email enabled={config.get('communication',{}).get('email',{}).get('enabled')}")
            config_path = os.path.join(BASE_DIR, 'config', 'default_config.json')
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
            print(f"[CONFIG SAVE] written to disk OK")
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
    print(f"[EMAIL CONFIG] received: {data}")

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

    print(f"[EMAIL CONFIG] saved. enabled={email_cfg.get('enabled')}, server={email_cfg.get('smtp_server')} (password redacted)")
    return jsonify({'success': True, 'saved': email_cfg})

@app.route('/api/email/test', methods=['POST'])
def email_test():
    """Send a test email to verify SMTP credentials"""
    if not background_scheduler or not background_scheduler.email_service:
        return jsonify({'error': 'Email service not available'}), 503
    try:
        es = background_scheduler.email_service
        print(f"[EMAIL TEST] global config enabled={config.get('communication',{}).get('email',{}).get('enabled')}")
        print(f"[EMAIL TEST] service.is_enabled={es.is_enabled}")
        _ecfg = es._get_config().get('communication',{}).get('email',{})
        _ecfg_safe = {k: ('***' if k == 'password' else v) for k, v in _ecfg.items()}
        print(f"[EMAIL TEST] getter email_cfg={_ecfg_safe}")
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
                'old_raw': r[2], 'new_raw': r[3],
                'old_type': type(r[2]).__name__,
                'new_type': type(r[3]).__name__,
                'reason': r[4], 'timestamp': r[5]
            })
        return jsonify({'rows': rows, 'count': len(rows)})
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/api/personality/history', methods=['GET'])
def personality_history():
    """Return recent personality trait changes"""
    try:
        cursor = ai_engine.db.get_connection().cursor()
        cursor.execute("""
            SELECT trait_name, old_value, new_value, change_reason, timestamp
            FROM personality_history
            ORDER BY timestamp DESC LIMIT 50
        """)
        rows = [{'trait': r[0], 'old': r[1], 'new': r[2],
                 'reason': r[3], 'timestamp': r[4]}
                for r in cursor.fetchall()]
        return jsonify({'history': rows})
    except Exception as e:
        return jsonify({'history': [], 'error': str(e)})

@app.route('/api/personality/force-evolve', methods=['POST'])
def force_evolve():
    """Manually trigger a personality evolution tick for testing"""
    try:
        # Always reload fresh from DB
        ai_engine.load_personality()

        # Log what we actually loaded
        print(f"[FORCE-EVOLVE] personality dict after load: {ai_engine.personality}")

        # Also check direct DB query for comparison
        cursor = ai_engine.db.get_connection().cursor()
        cursor.execute("SELECT trait_name, trait_value FROM personality_traits WHERE is_active=1")
        db_vals = {row[0]: row[1] for row in cursor.fetchall()}
        print(f"[FORCE-EVOLVE] DB values: {db_vals}")

        msg  = request.json.get('message', 'haha that is so funny, can you explain in detail how this algorithm works? be creative and curious')
        resp = request.json.get('response', 'I think that is fascinating! I wonder what deeper patterns exist here? Let me explore this with you.')
        before = dict(ai_engine.personality)
        ai_engine.evolve_personality_gradually(msg, resp)
        after = ai_engine.personality
        diff = {k: round(float(after[k]) - float(before.get(k, 0.5)), 4) for k in after}
        # Also fetch the most recent history entries to verify they were written correctly
        cursor.execute("SELECT trait_name, old_value, new_value, change_reason FROM personality_history ORDER BY id DESC LIMIT 10")
        recent_history = [{'trait': r[0], 'old': r[1], 'new': r[2], 'reason': r[3]} for r in cursor.fetchall()]
        return jsonify({'success': True, 'personality': after, 'db_at_load': db_vals, 'changes': diff, 'recent_history': recent_history})
    except Exception as e:
        import traceback
        return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500

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
