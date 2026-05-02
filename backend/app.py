import os
import json
import random
import datetime
import hashlib
import hmac
from functools import wraps

from flask import Flask, request, jsonify, g
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS

from config import Config
from models import db, Course, Question, Summary, TestSession
from utils.pdf_parser import extract_text_from_pdf, chunk_text
from utils.ai_service import generate_questions, generate_summary

# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # ── Logging setup ────────────────────────────────────────────
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] %(levelname)s %(name)s: %(message)s',
        datefmt='%H:%M:%S',
    )
    app.logger.setLevel(logging.INFO)

    db.init_app(app)
    CORS(app, resources={r"/api/*": {"origins": app.config['CORS_ORIGINS']}})

    with app.app_context():
        db.create_all()

    # ── Log every request + any unhandled exceptions ─────────────
    @app.before_request
    def log_request():
        from flask import request as req
        app.logger.info(f"--> {req.method} {req.path}")

    @app.after_request
    def log_response(response):
        from flask import request as req
        level = logging.WARNING if response.status_code >= 400 else logging.INFO
        app.logger.log(level, f"<-- {req.method} {req.path} {response.status_code}")
        return response

    @app.teardown_request
    def log_exception(exc):
        if exc is not None:
            app.logger.exception(f"Unhandled exception on {exc}")

    # Register blueprints / routes
    register_routes(app)

    return app


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------

def _make_token(username: str, secret: str) -> str:
    import base64
    payload = json.dumps({
        'sub': username,
        'exp': (datetime.datetime.utcnow() + datetime.timedelta(hours=Config.JWT_EXPIRY_HOURS)).isoformat(),
    })
    payload_b64 = base64.urlsafe_b64encode(payload.encode()).decode()
    sig = hmac.new(secret.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"


def _verify_token(token: str, secret: str):
    import base64
    try:
        parts = token.split('.')
        if len(parts) != 2:
            return None
        payload_b64, sig = parts
        expected_sig = hmac.new(secret.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        payload = json.loads(base64.urlsafe_b64decode(payload_b64 + '==').decode())
        exp = datetime.datetime.fromisoformat(payload['exp'])
        if datetime.datetime.utcnow() > exp:
            return None
        return payload
    except Exception:
        return None


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get('Authorization', '')
        if not auth.startswith('Bearer '):
            return jsonify({'error': 'Unauthorized'}), 401
        token = auth[7:]
        payload = _verify_token(token, Config.JWT_SECRET_KEY)
        if not payload:
            return jsonify({'error': 'Token expired or invalid'}), 401
        g.admin_user = payload['sub']
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------

def register_routes(app: Flask):

    # -----------------------------------------------------------------------
    # Health
    # -----------------------------------------------------------------------
    @app.route('/api/health')
    def health():
        return jsonify({'status': 'ok', 'service': 'CBT Mock AI'})

    # -----------------------------------------------------------------------
    # Auth
    # -----------------------------------------------------------------------
    @app.route('/api/auth/login', methods=['POST'])
    def login():
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body required'}), 400

        username = data.get('username', '').strip()
        password = data.get('password', '').strip()

        if username == Config.ADMIN_USERNAME and password == Config.ADMIN_PASSWORD:
            token = _make_token(username, Config.JWT_SECRET_KEY)
            return jsonify({'token': token, 'username': username})

        return jsonify({'error': 'Invalid credentials'}), 401

    @app.route('/api/auth/verify', methods=['GET'])
    @require_auth
    def verify_token():
        return jsonify({'valid': True, 'username': g.admin_user})

    # -----------------------------------------------------------------------
    # Courses — public
    # -----------------------------------------------------------------------
    @app.route('/api/courses', methods=['GET'])
    def get_courses():
        """Return all published courses (for student search)."""
        search = request.args.get('q', '').strip()
        query = Course.query.filter_by(published=True)
        if search:
            query = query.filter(Course.name.ilike(f'%{search}%'))
        courses = query.order_by(Course.name).all()
        return jsonify([c.to_dict() for c in courses])

    @app.route('/api/courses/<int:course_id>', methods=['GET'])
    def get_course(course_id):
        course = Course.query.get_or_404(course_id)
        return jsonify(course.to_dict())

    # -----------------------------------------------------------------------
    # Courses — admin
    # -----------------------------------------------------------------------
    @app.route('/api/admin/courses', methods=['GET'])
    @require_auth
    def admin_get_courses():
        """Return all courses (published + unpublished) for admin."""
        courses = Course.query.order_by(Course.created_at.desc()).all()
        return jsonify([c.to_dict() for c in courses])

    @app.route('/api/admin/courses/<int:course_id>', methods=['DELETE'])
    @require_auth
    def admin_delete_course(course_id):
        course = Course.query.get_or_404(course_id)
        db.session.delete(course)
        db.session.commit()
        return jsonify({'message': f'Course "{course.name}" deleted.'})

    @app.route('/api/admin/courses/<int:course_id>/publish', methods=['POST'])
    @require_auth
    def admin_publish_course(course_id):
        course = Course.query.get_or_404(course_id)
        approved_q = [q for q in course.questions if q.approved]

        if len(approved_q) < 40:
            return jsonify({
                'error': f'Cannot publish: only {len(approved_q)} approved questions. Need at least 40.'
            }), 400

        if not course.summaries:
            return jsonify({'error': 'Cannot publish: no summary available.'}), 400

        course.published = True
        db.session.commit()
        return jsonify({'message': f'Course "{course.name}" is now published.', 'course': course.to_dict()})

    @app.route('/api/admin/courses/<int:course_id>/unpublish', methods=['POST'])
    @require_auth
    def admin_unpublish_course(course_id):
        course = Course.query.get_or_404(course_id)
        course.published = False
        db.session.commit()
        return jsonify({'message': f'Course "{course.name}" unpublished.', 'course': course.to_dict()})

    # -----------------------------------------------------------------------
    # PDF Upload & AI Generation
    # -----------------------------------------------------------------------
    @app.route('/api/upload-pdf', methods=['POST'])
    @require_auth
    def upload_pdf():
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400

        file = request.files['file']
        course_name = request.form.get('course_name', '').strip()

        if not course_name:
            return jsonify({'error': 'Course name is required'}), 400

        if not file.filename or not file.filename.lower().endswith('.pdf'):
            return jsonify({'error': 'Only PDF files are accepted'}), 400

        file_bytes = file.read()
        if len(file_bytes) == 0:
            return jsonify({'error': 'Uploaded file is empty'}), 400

        # Extract text
        try:
            text = extract_text_from_pdf(file_bytes)
        except ValueError as e:
            return jsonify({'error': str(e)}), 422

        # Chunk for AI
        # Chunk size is provider-aware (Groq: 7k chars, others: 10k)
        chunked_text = chunk_text(text)

        # Get or create course
        existing = Course.query.filter(
            Course.name.ilike(course_name)
        ).first()

        if existing:
            course = existing
            # Clear old unapproved questions and summary for regeneration
            Question.query.filter_by(course_id=course.id, approved=False).delete()
            Summary.query.filter_by(course_id=course.id).delete()
        else:
            course = Course(name=course_name)
            db.session.add(course)
            db.session.flush()

        # Generate with AI — provider + key come from env via ai_service
        warning = ""
        try:
            questions, warning = generate_questions(chunked_text, course_name)
        except ValueError as e:
            db.session.rollback()
            app.logger.error(f"[upload-pdf] Question generation ValueError: {e}")
            return jsonify({'error': f'Question generation failed: {str(e)}'}), 422
        except ImportError as e:
            db.session.rollback()
            app.logger.error(f"[upload-pdf] Missing package: {e}")
            return jsonify({'error': f'Missing AI package: {str(e)}'}), 503
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"[upload-pdf] Question generation error: {type(e).__name__}: {e}")
            return jsonify({'error': f'AI error ({type(e).__name__}): {str(e)}'}), 500

        try:
            summary_html = generate_summary(chunked_text, course_name)
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"[upload-pdf] Summary generation error: {type(e).__name__}: {e}")
            return jsonify({'error': f'Summary generation failed ({type(e).__name__}): {str(e)}'}), 500

        # Save questions
        for q_data in questions:
            q = Question(
                course_id=course.id,
                question=q_data['question'],
                option_a=q_data['option_a'],
                option_b=q_data['option_b'],
                option_c=q_data['option_c'],
                option_d=q_data['option_d'],
                correct_answer=q_data['correct_answer'],
                explanation=q_data.get('explanation', ''),
                approved=False,
            )
            db.session.add(q)

        # Save summary
        summary = Summary(course_id=course.id, content=summary_html)
        db.session.add(summary)

        db.session.commit()

        return jsonify({
            'message': 'PDF processed successfully.',
            'course': course.to_dict(),
            'questions_generated': len(questions),
            'warning': warning,
        }), 201

    # -----------------------------------------------------------------------
    # Questions — admin
    # -----------------------------------------------------------------------
    @app.route('/api/admin/courses/<int:course_id>/questions', methods=['GET'])
    @require_auth
    def admin_get_questions(course_id):
        Course.query.get_or_404(course_id)
        questions = Question.query.filter_by(course_id=course_id).all()
        return jsonify([q.to_dict(include_answer=True) for q in questions])

    @app.route('/api/admin/questions/<int:question_id>', methods=['PUT'])
    @require_auth
    def admin_update_question(question_id):
        q = Question.query.get_or_404(question_id)
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        if 'question' in data:
            q.question = data['question'].strip()
        if 'option_a' in data:
            q.option_a = data['option_a'].strip()
        if 'option_b' in data:
            q.option_b = data['option_b'].strip()
        if 'option_c' in data:
            q.option_c = data['option_c'].strip()
        if 'option_d' in data:
            q.option_d = data['option_d'].strip()
        if 'correct_answer' in data:
            answer = data['correct_answer'].upper()
            if answer not in ('A', 'B', 'C', 'D'):
                return jsonify({'error': 'correct_answer must be A, B, C, or D'}), 400
            q.correct_answer = answer
        if 'explanation' in data:
            q.explanation = data['explanation'].strip()
        if 'approved' in data:
            q.approved = bool(data['approved'])

        db.session.commit()
        return jsonify(q.to_dict(include_answer=True))

    @app.route('/api/admin/questions/<int:question_id>', methods=['DELETE'])
    @require_auth
    def admin_delete_question(question_id):
        q = Question.query.get_or_404(question_id)
        db.session.delete(q)
        db.session.commit()
        return jsonify({'message': 'Question deleted.'})

    @app.route('/api/admin/questions/<int:question_id>/approve', methods=['POST'])
    @require_auth
    def admin_approve_question(question_id):
        q = Question.query.get_or_404(question_id)
        course = q.course
        approved_count = Question.query.filter_by(course_id=course.id, approved=True).count()

        if not q.approved and approved_count >= 40:
            return jsonify({'error': 'Already have 40 approved questions. Remove one before approving another.'}), 400

        q.approved = not q.approved
        db.session.commit()
        return jsonify({'approved': q.approved, 'question': q.to_dict(include_answer=True)})

    @app.route('/api/admin/courses/<int:course_id>/approve-all', methods=['POST'])
    @require_auth
    def admin_approve_first_40(course_id):
        """Approve the first 40 questions for a course in one action."""
        questions = Question.query.filter_by(course_id=course_id, approved=False).limit(40).all()
        count = 0
        for q in questions:
            q.approved = True
            count += 1
        db.session.commit()
        return jsonify({'message': f'{count} questions approved.', 'count': count})

    # -----------------------------------------------------------------------
    # Summary — admin
    # -----------------------------------------------------------------------
    @app.route('/api/admin/courses/<int:course_id>/summary', methods=['GET'])
    @require_auth
    def admin_get_summary(course_id):
        summary = Summary.query.filter_by(course_id=course_id).first()
        if not summary:
            return jsonify({'error': 'No summary found'}), 404
        return jsonify(summary.to_dict())

    @app.route('/api/admin/courses/<int:course_id>/summary', methods=['PUT'])
    @require_auth
    def admin_update_summary(course_id):
        summary = Summary.query.filter_by(course_id=course_id).first()
        if not summary:
            return jsonify({'error': 'No summary found'}), 404
        data = request.get_json()
        if not data or 'content' not in data:
            return jsonify({'error': 'content field required'}), 400
        summary.content = data['content'].strip()
        summary.updated_at = datetime.datetime.utcnow()
        db.session.commit()
        return jsonify(summary.to_dict())

    # -----------------------------------------------------------------------
    # Exam — public (student)
    # -----------------------------------------------------------------------
    @app.route('/api/get-questions/<int:course_id>', methods=['GET'])
    def get_questions(course_id):
        """Return 40 randomised approved questions (without correct answers) for a course."""
        course = Course.query.get_or_404(course_id)
        if not course.published:
            return jsonify({'error': 'This course is not published yet.'}), 403

        questions = Question.query.filter_by(course_id=course_id, approved=True).all()
        if len(questions) < 40:
            return jsonify({
                'error': f'Not enough questions available ({len(questions)}/40). Please check back later.'
            }), 409

        selected = random.sample(questions, 40)
        return jsonify({
            'course': course.to_dict(),
            'questions': [q.to_dict(include_answer=False) for q in selected],
            'total': 40,
        })

    @app.route('/api/submit-test', methods=['POST'])
    def submit_test():
        """Grade a submitted exam."""
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body required'}), 400

        course_id = data.get('course_id')
        answers = data.get('answers', {})  # {question_id: chosen_option}

        if not course_id:
            return jsonify({'error': 'course_id required'}), 400

        course = Course.query.get_or_404(course_id)

        results = []
        score = 0
        total = len(answers)

        for q_id_str, chosen in answers.items():
            try:
                q_id = int(q_id_str)
                q = Question.query.get(q_id)
                if not q or q.course_id != course_id:
                    continue
                is_correct = chosen.upper() == q.correct_answer.upper()
                if is_correct:
                    score += 1
                results.append({
                    'question_id': q_id,
                    'question': q.question,
                    'option_a': q.option_a,
                    'option_b': q.option_b,
                    'option_c': q.option_c,
                    'option_d': q.option_d,
                    'chosen': chosen.upper() if chosen else None,
                    'correct_answer': q.correct_answer,
                    'is_correct': is_correct,
                    'explanation': q.explanation,
                })
            except (ValueError, AttributeError):
                continue

        total = len(results)

        # Save session
        session = TestSession(
            course_id=course_id,
            score=score,
            total=total,
            answers=json.dumps(answers),
        )
        db.session.add(session)
        db.session.commit()

        return jsonify({
            'session_id': session.id,
            'score': score,
            'total': total,
            'percentage': round((score / total) * 100, 1) if total > 0 else 0,
            'results': results,
            'course_name': course.name,
        })

    # -----------------------------------------------------------------------
    # Summary — public (student)
    # -----------------------------------------------------------------------
    @app.route('/api/get-summary/<int:course_id>', methods=['GET'])
    def get_summary(course_id):
        course = Course.query.get_or_404(course_id)
        if not course.published:
            return jsonify({'error': 'This course is not published yet.'}), 403
        summary = Summary.query.filter_by(course_id=course_id).first()
        if not summary:
            return jsonify({'error': 'No summary available for this course.'}), 404
        return jsonify({
            'course': course.to_dict(),
            'summary': summary.to_dict(),
        })

    # -----------------------------------------------------------------------
    # Admin stats
    # -----------------------------------------------------------------------
    @app.route('/api/admin/stats', methods=['GET'])
    @require_auth
    def admin_stats():
        total_courses = Course.query.count()
        published = Course.query.filter_by(published=True).count()
        total_q = Question.query.count()
        total_sessions = TestSession.query.count()

        sessions = TestSession.query.all()
        avg_score = 0
        if sessions:
            avg_score = round(
                sum((s.score / s.total * 100) if s.total else 0 for s in sessions) / len(sessions), 1
            )

        return jsonify({
            'total_courses': total_courses,
            'published_courses': published,
            'total_questions': total_q,
            'total_test_sessions': total_sessions,
            'average_score_percent': avg_score,
        })

    @app.route('/api/admin/diagnose', methods=['GET'])
    @require_auth
    def admin_diagnose():
        """
        Diagnose the server environment — checks DB, AI provider,
        installed packages, and env vars. Useful for debugging 502 errors.
        """
        import importlib
        import os

        results = {}

        # ── Database ────────────────────────────────────────────
        try:
            db.session.execute(db.text('SELECT 1'))
            results['database'] = {'ok': True, 'url': Config.SQLALCHEMY_DATABASE_URI[:40] + '...'}
        except Exception as e:
            results['database'] = {'ok': False, 'error': str(e)}

        # ── AI provider config ──────────────────────────────────
        provider = os.getenv('AI_PROVIDER', 'groq')
        key_map = {
            'groq':   ('GROQ_API_KEY',   os.getenv('GROQ_API_KEY',   '')),
            'gemini': ('GEMINI_API_KEY',  os.getenv('GEMINI_API_KEY', '')),
            'openai': ('OPENAI_API_KEY',  os.getenv('OPENAI_API_KEY', '')),
        }
        key_name, key_value = key_map.get(provider, ('UNKNOWN', ''))
        results['ai'] = {
            'provider': provider,
            'key_name': key_name,
            'key_set':  bool(key_value),
            'key_prefix': key_value[:8] + '...' if key_value else 'NOT SET',
        }

        # ── Packages ─────────────────────────────────────────────
        packages = {
            'openai':             'openai',
            'flask':              'flask',
            'flask_sqlalchemy':   'flask_sqlalchemy',
            'fitz (PyMuPDF)':     'fitz',
            'pdfplumber':         'pdfplumber',
            'psycopg2':           'psycopg2',
            'google.generativeai':'google.generativeai',
        }
        pkg_results = {}
        for label, mod in packages.items():
            try:
                importlib.import_module(mod)
                pkg_results[label] = 'installed'
            except ImportError:
                pkg_results[label] = 'MISSING'
        results['packages'] = pkg_results

        # ── Upload folder ────────────────────────────────────────
        results['upload_folder'] = {
            'path':     Config.UPLOAD_FOLDER,
            'exists':   os.path.isdir(Config.UPLOAD_FOLDER),
            'writable': os.access(Config.UPLOAD_FOLDER, os.W_OK),
        }

        # ── Overall status ───────────────────────────────────────
        all_ok = (
            results['database']['ok'] and
            results['ai']['key_set'] and
            results['packages'].get('openai') == 'installed'
        )
        results['status'] = 'ok' if all_ok else 'issues_found'

        return jsonify(results)

    @app.route('/api/admin/ai-provider', methods=['GET'])
    @require_auth
    def admin_ai_provider():
        from utils.ai_service import get_active_provider
        return jsonify(get_active_provider())

    # -----------------------------------------------------------------------
    # Error handlers
    # -----------------------------------------------------------------------
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({'error': 'Resource not found'}), 404

    @app.errorhandler(413)
    def too_large(e):
        return jsonify({'error': 'File too large. Maximum size is 20MB.'}), 413

    @app.errorhandler(500)
    def server_error(e):
        return jsonify({'error': 'Internal server error'}), 500


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

app = create_app()

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_ENV', 'production') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)
