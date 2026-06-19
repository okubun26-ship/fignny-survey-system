import sqlite3
import os
from werkzeug.security import generate_password_hash

DATABASE = os.path.join(os.path.dirname(__file__), 'survey.db')

DDL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    user_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    email        VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role         VARCHAR(20)  NOT NULL DEFAULT 'general',
    display_name VARCHAR(100),
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at   DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS surveys (
    survey_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    created_by  INTEGER NOT NULL REFERENCES users(user_id),
    title       VARCHAR(255) NOT NULL,
    description TEXT,
    deadline    DATETIME,
    status      VARCHAR(20) NOT NULL DEFAULT 'open',
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS questions (
    question_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    survey_id     INTEGER NOT NULL REFERENCES surveys(survey_id),
    question_text TEXT NOT NULL,
    question_type VARCHAR(20) NOT NULL,
    is_required   BOOLEAN NOT NULL DEFAULT 1,
    display_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS question_options (
    option_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id   INTEGER NOT NULL REFERENCES questions(question_id),
    option_text   VARCHAR(255) NOT NULL,
    display_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS answers (
    answer_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    survey_id    INTEGER NOT NULL REFERENCES surveys(survey_id),
    user_id      INTEGER NOT NULL REFERENCES users(user_id),
    status       VARCHAR(20) NOT NULL DEFAULT 'completed',
    submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(survey_id, user_id)
);

CREATE TABLE IF NOT EXISTS answer_details (
    detail_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    answer_id          INTEGER NOT NULL REFERENCES answers(answer_id),
    question_id        INTEGER NOT NULL REFERENCES questions(question_id),
    answer_text        TEXT,
    selected_option_id INTEGER REFERENCES question_options(option_id),
    yes_no_value       BOOLEAN
);
"""


def init_db():
    db = sqlite3.connect(DATABASE)
    db.executescript(DDL)

    if not db.execute("SELECT 1 FROM users WHERE email = 'satomi@example.com'").fetchone():
        db.execute(
            "INSERT INTO users (email, password_hash, role, display_name) VALUES (?,?,?,?)",
            ('satomi@example.com', generate_password_hash('fignny'), 'admin', '里見 恵介'),
        )
        db.commit()
        print("管理者ユーザーを作成しました: satomi@example.com / fignny")

    db.close()


if __name__ == '__main__':
    init_db()
    print("データベースを初期化しました。")
