import os
import secrets
import sqlite3
from functools import wraps

from flask import (Flask, g, render_template, request,
                   redirect, url_for, session, flash)
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))

DATABASE = os.path.join(os.path.dirname(__file__), 'survey.db')


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def get_db():
    db = getattr(g, '_db', None)
    if db is None:
        db = g._db = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys = ON')
    return db


@app.teardown_appcontext
def close_db(_exc):
    db = getattr(g, '_db', None)
    if db is not None:
        db.close()


# ---------------------------------------------------------------------------
# Auth decorators
# ---------------------------------------------------------------------------

def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapped


def admin_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        if session.get('role') != 'admin':
            flash('この操作は管理者のみ可能です', 'error')
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return wrapped


# ---------------------------------------------------------------------------
# S01: ログイン
# ---------------------------------------------------------------------------

@app.route('/', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('home'))
    error = None
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        if user and check_password_hash(user['password_hash'], password):
            session.clear()
            session['user_id'] = user['user_id']
            session['role'] = user['role']
            session['display_name'] = user['display_name']
            return redirect(url_for('home'))
        error = 'メールアドレスまたはパスワードが正しくありません'
    return render_template('login.html', error=error)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ---------------------------------------------------------------------------
# S02: ホーム画面
# ---------------------------------------------------------------------------

@app.route('/home')
@login_required
def home():
    db = get_db()

    surveys = db.execute(
        """SELECT s.survey_id, s.title, s.deadline, s.status, s.created_by
           FROM surveys s
           WHERE s.status = 'open'
           ORDER BY s.created_at DESC"""
    ).fetchall()

    survey_list = []
    for s in surveys:
        answered = db.execute(
            'SELECT 1 FROM answers WHERE survey_id = ? AND user_id = ?',
            (s['survey_id'], session['user_id'])
        ).fetchone() is not None
        survey_list.append({
            'survey_id': s['survey_id'],
            'title': s['title'],
            'deadline': s['deadline'],
            'answered': answered,
            'created_by': s['created_by'],
        })

    admin_surveys = []
    if session['role'] == 'admin':
        rows = db.execute(
            """SELECT s.survey_id, s.title, s.deadline, s.status,
                      COUNT(a.answer_id) AS answered_count
               FROM surveys s
               LEFT JOIN answers a ON s.survey_id = a.survey_id
               WHERE s.created_by = ?
               GROUP BY s.survey_id
               ORDER BY s.created_at DESC""",
            (session['user_id'],)
        ).fetchall()
        total = db.execute(
            "SELECT COUNT(*) AS cnt FROM users WHERE role = 'general'"
        ).fetchone()['cnt']
        for row in rows:
            admin_surveys.append({
                'survey_id': row['survey_id'],
                'title': row['title'],
                'deadline': row['deadline'],
                'status': row['status'],
                'answered_count': row['answered_count'],
                'total_users': total,
            })

    return render_template('home.html',
                           survey_list=survey_list,
                           admin_surveys=admin_surveys)


# ---------------------------------------------------------------------------
# S03: アンケート作成
# ---------------------------------------------------------------------------

@app.route('/survey/create', methods=['GET', 'POST'])
@admin_required
def survey_create():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        deadline = request.form.get('deadline', '').strip() or None
        errors = []

        if not title:
            errors.append('アンケートタイトルは必須です')

        question_count = int(request.form.get('question_count', 0))
        questions = []
        for i in range(question_count):
            q_text = request.form.get(f'question_text_{i}', '').strip()
            q_type = request.form.get(f'question_type_{i}', 'free_text')
            q_req = request.form.get(f'question_required_{i}', 'required') == 'required'
            options = []
            if q_type == 'dropdown':
                opt_count = int(request.form.get(f'option_count_{i}', 0))
                for j in range(opt_count):
                    opt = request.form.get(f'option_{i}_{j}', '').strip()
                    if opt:
                        options.append(opt)
                if len(options) < 2:
                    errors.append(f'質問{i + 1}: プルダウン形式の選択肢は2件以上必要です')
            if not q_text:
                errors.append(f'質問{i + 1}: 質問文は必須です')
            questions.append({'text': q_text, 'type': q_type,
                              'required': q_req, 'options': options})

        if question_count == 0:
            errors.append('質問を1件以上追加してください')

        if not errors:
            db = get_db()
            cur = db.execute(
                'INSERT INTO surveys (created_by, title, description, deadline, status) VALUES (?,?,?,?,?)',
                (session['user_id'], title, description, deadline, 'open')
            )
            survey_id = cur.lastrowid
            for idx, q in enumerate(questions):
                cur2 = db.execute(
                    'INSERT INTO questions (survey_id, question_text, question_type, is_required, display_order) VALUES (?,?,?,?,?)',
                    (survey_id, q['text'], q['type'], q['required'], idx)
                )
                q_id = cur2.lastrowid
                for oidx, opt in enumerate(q['options']):
                    db.execute(
                        'INSERT INTO question_options (question_id, option_text, display_order) VALUES (?,?,?)',
                        (q_id, opt, oidx)
                    )
            db.commit()
            flash('アンケートを公開しました', 'success')
            return redirect(url_for('home'))

        return render_template('survey_create.html', errors=errors)

    return render_template('survey_create.html', errors=[])


# ---------------------------------------------------------------------------
# S04: アンケート回答
# ---------------------------------------------------------------------------

@app.route('/survey/<int:survey_id>/answer', methods=['GET', 'POST'])
@login_required
def survey_answer(survey_id):
    db = get_db()
    survey = db.execute('SELECT * FROM surveys WHERE survey_id = ?', (survey_id,)).fetchone()
    if not survey:
        flash('アンケートが見つかりません', 'error')
        return redirect(url_for('home'))

    questions = db.execute(
        'SELECT * FROM questions WHERE survey_id = ? ORDER BY display_order', (survey_id,)
    ).fetchall()

    q_with_opts = []
    for q in questions:
        opts = (
            db.execute(
                'SELECT * FROM question_options WHERE question_id = ? ORDER BY display_order',
                (q['question_id'],)
            ).fetchall()
            if q['question_type'] == 'dropdown' else []
        )
        q_with_opts.append({'q': q, 'options': opts})

    existing = db.execute(
        'SELECT * FROM answers WHERE survey_id = ? AND user_id = ?',
        (survey_id, session['user_id'])
    ).fetchone()

    if existing:
        details = db.execute(
            """SELECT ad.*, q.question_text, q.question_type, qo.option_text
               FROM answer_details ad
               JOIN questions q ON ad.question_id = q.question_id
               LEFT JOIN question_options qo ON ad.selected_option_id = qo.option_id
               WHERE ad.answer_id = ?
               ORDER BY q.display_order""",
            (existing['answer_id'],)
        ).fetchall()
        return render_template('survey_answer.html',
                               survey=survey, q_with_opts=q_with_opts,
                               readonly=True, details=details, errors=[])

    if request.method == 'POST':
        errors = []
        for item in q_with_opts:
            q = item['q']
            if q['is_required']:
                val = request.form.get(f'answer_{q["question_id"]}', '').strip()
                if not val:
                    errors.append(f'「{q["question_text"]}」は必須項目です')

        if not errors:
            cur = db.execute(
                'INSERT INTO answers (survey_id, user_id, status) VALUES (?,?,?)',
                (survey_id, session['user_id'], 'completed')
            )
            answer_id = cur.lastrowid
            for item in q_with_opts:
                q = item['q']
                qid = q['question_id']
                qtype = q['question_type']
                val = request.form.get(f'answer_{qid}', '').strip()
                if qtype == 'free_text':
                    db.execute(
                        'INSERT INTO answer_details (answer_id, question_id, answer_text) VALUES (?,?,?)',
                        (answer_id, qid, val or None)
                    )
                elif qtype == 'dropdown':
                    db.execute(
                        'INSERT INTO answer_details (answer_id, question_id, selected_option_id) VALUES (?,?,?)',
                        (answer_id, qid, int(val) if val else None)
                    )
                elif qtype == 'yes_no':
                    yes_no = True if val == 'yes' else (False if val == 'no' else None)
                    db.execute(
                        'INSERT INTO answer_details (answer_id, question_id, yes_no_value) VALUES (?,?,?)',
                        (answer_id, qid, yes_no)
                    )
            db.commit()
            flash('回答を送信しました', 'success')
            return redirect(url_for('home'))

        return render_template('survey_answer.html',
                               survey=survey, q_with_opts=q_with_opts,
                               readonly=False, details=None, errors=errors)

    return render_template('survey_answer.html',
                           survey=survey, q_with_opts=q_with_opts,
                           readonly=False, details=None, errors=[])


# ---------------------------------------------------------------------------
# S05: 集計結果
# ---------------------------------------------------------------------------

@app.route('/survey/<int:survey_id>/results')
@admin_required
def survey_results(survey_id):
    db = get_db()
    survey = db.execute('SELECT * FROM surveys WHERE survey_id = ?', (survey_id,)).fetchone()
    if not survey:
        flash('アンケートが見つかりません', 'error')
        return redirect(url_for('home'))

    total_users = db.execute(
        "SELECT COUNT(*) AS cnt FROM users WHERE role = 'general'"
    ).fetchone()['cnt']
    answered_count = db.execute(
        'SELECT COUNT(*) AS cnt FROM answers WHERE survey_id = ?', (survey_id,)
    ).fetchone()['cnt']
    unanswered = db.execute(
        """SELECT display_name FROM users
           WHERE role = 'general'
             AND user_id NOT IN (SELECT user_id FROM answers WHERE survey_id = ?)
           ORDER BY display_name""",
        (survey_id,)
    ).fetchall()

    questions = db.execute(
        'SELECT * FROM questions WHERE survey_id = ? ORDER BY display_order', (survey_id,)
    ).fetchall()

    results = []
    for q in questions:
        qid = q['question_id']
        qtype = q['question_type']
        if qtype == 'free_text':
            rows = db.execute(
                """SELECT ad.answer_text, u.display_name
                   FROM answer_details ad
                   JOIN answers a ON ad.answer_id = a.answer_id
                   JOIN users u ON a.user_id = u.user_id
                   WHERE ad.question_id = ?
                   ORDER BY a.submitted_at""",
                (qid,)
            ).fetchall()
            results.append({'q': q, 'type': 'free_text', 'rows': rows})
        elif qtype == 'dropdown':
            opts = db.execute(
                """SELECT qo.option_text, COUNT(ad.detail_id) AS cnt
                   FROM question_options qo
                   LEFT JOIN answer_details ad
                     ON qo.option_id = ad.selected_option_id AND ad.question_id = ?
                   WHERE qo.question_id = ?
                   GROUP BY qo.option_id
                   ORDER BY qo.display_order""",
                (qid, qid)
            ).fetchall()
            results.append({'q': q, 'type': 'dropdown', 'opts': opts})
        elif qtype == 'yes_no':
            yes_cnt = db.execute(
                'SELECT COUNT(*) AS cnt FROM answer_details WHERE question_id = ? AND yes_no_value = 1',
                (qid,)
            ).fetchone()['cnt']
            no_cnt = db.execute(
                'SELECT COUNT(*) AS cnt FROM answer_details WHERE question_id = ? AND yes_no_value = 0',
                (qid,)
            ).fetchone()['cnt']
            results.append({'q': q, 'type': 'yes_no', 'yes': yes_cnt, 'no': no_cnt})

    return render_template('survey_results.html',
                           survey=survey,
                           total_users=total_users,
                           answered_count=answered_count,
                           unanswered=unanswered,
                           results=results)


# ---------------------------------------------------------------------------
# ユーザー管理（管理者専用）
# ---------------------------------------------------------------------------

@app.route('/users')
@admin_required
def user_manage():
    db = get_db()
    users = db.execute(
        'SELECT user_id, email, role, display_name, created_at FROM users ORDER BY created_at'
    ).fetchall()
    return render_template('user_manage.html', users=users, new_user=None)


@app.route('/users/create', methods=['POST'])
@admin_required
def user_create():
    email = request.form.get('email', '').strip()
    display_name = request.form.get('display_name', '').strip()
    role = request.form.get('role', 'general')
    db = get_db()

    if not email or not display_name:
        flash('メールアドレスと表示名は必須です', 'error')
        return redirect(url_for('user_manage'))

    if db.execute('SELECT 1 FROM users WHERE email = ?', (email,)).fetchone():
        flash('そのメールアドレスはすでに登録されています', 'error')
        return redirect(url_for('user_manage'))

    password = secrets.token_urlsafe(8)
    db.execute(
        'INSERT INTO users (email, password_hash, role, display_name) VALUES (?,?,?,?)',
        (email, generate_password_hash(password), role, display_name)
    )
    db.commit()

    users = db.execute(
        'SELECT user_id, email, role, display_name, created_at FROM users ORDER BY created_at'
    ).fetchall()
    return render_template('user_manage.html', users=users,
                           new_user={'email': email, 'password': password,
                                     'display_name': display_name})


# ---------------------------------------------------------------------------
# エントリポイント
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    from init_db import init_db
    init_db()
    app.run(debug=True, host='127.0.0.1', port=5000)
