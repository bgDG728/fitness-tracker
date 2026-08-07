"""
健身飲食訓練紀錄系統的資料庫層。用 SQLite,單一使用者、本機檔案儲存
(fitness.db),不需要額外架設資料庫伺服器。
"""

import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path

DB_PATH = Path(__file__).parent / "fitness.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS profile (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    height_cm REAL,
    age INTEGER,
    sex TEXT CHECK (sex IN ('male', 'female')),
    activity_level TEXT,
    goal TEXT,
    target_calories REAL,
    target_protein_g REAL,
    target_carb_g REAL,
    target_fat_g REAL
);

CREATE TABLE IF NOT EXISTS body_weight_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    log_date TEXT NOT NULL,
    weight_kg REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS food_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    log_date TEXT NOT NULL,
    meal_name TEXT NOT NULL,
    calories REAL NOT NULL,
    protein_g REAL DEFAULT 0,
    carb_g REAL DEFAULT 0,
    fat_g REAL DEFAULT 0,
    note TEXT
);

CREATE TABLE IF NOT EXISTS workout_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    log_date TEXT NOT NULL,
    exercise TEXT NOT NULL,
    set_number INTEGER NOT NULL,
    reps INTEGER NOT NULL,
    weight_kg REAL NOT NULL,
    note TEXT
);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)


# ---- profile ----

def get_profile():
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM profile WHERE id = 1").fetchone()
        return dict(row) if row else None


def save_profile(height_cm, age, sex, activity_level, goal,
                  target_calories, target_protein_g, target_carb_g, target_fat_g):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO profile (id, height_cm, age, sex, activity_level, goal,
                                  target_calories, target_protein_g, target_carb_g, target_fat_g)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                height_cm=excluded.height_cm,
                age=excluded.age,
                sex=excluded.sex,
                activity_level=excluded.activity_level,
                goal=excluded.goal,
                target_calories=excluded.target_calories,
                target_protein_g=excluded.target_protein_g,
                target_carb_g=excluded.target_carb_g,
                target_fat_g=excluded.target_fat_g
            """,
            (height_cm, age, sex, activity_level, goal,
             target_calories, target_protein_g, target_carb_g, target_fat_g),
        )


# ---- body weight ----

def add_body_weight(weight_kg, log_date=None):
    log_date = log_date or date.today().isoformat()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO body_weight_log (log_date, weight_kg) VALUES (?, ?)",
            (log_date, weight_kg),
        )


def get_body_weight_log():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM body_weight_log ORDER BY log_date ASC"
        ).fetchall()
        return [dict(r) for r in rows]


def get_latest_body_weight():
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM body_weight_log ORDER BY log_date DESC, id DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None


# ---- food log ----

def add_food(meal_name, calories, protein_g, carb_g, fat_g, note="", log_date=None):
    log_date = log_date or date.today().isoformat()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO food_log (log_date, meal_name, calories, protein_g, carb_g, fat_g, note)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (log_date, meal_name, calories, protein_g, carb_g, fat_g, note),
        )


def get_food_log(log_date=None):
    with get_conn() as conn:
        if log_date:
            rows = conn.execute(
                "SELECT * FROM food_log WHERE log_date = ? ORDER BY id ASC", (log_date,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM food_log ORDER BY log_date ASC, id ASC"
            ).fetchall()
        return [dict(r) for r in rows]


def delete_food(food_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM food_log WHERE id = ?", (food_id,))


# ---- workout log ----

def add_workout_set(exercise, set_number, reps, weight_kg, note="", log_date=None):
    log_date = log_date or date.today().isoformat()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO workout_log (log_date, exercise, set_number, reps, weight_kg, note)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (log_date, exercise, set_number, reps, weight_kg, note),
        )


def get_workout_log(log_date=None):
    with get_conn() as conn:
        if log_date:
            rows = conn.execute(
                "SELECT * FROM workout_log WHERE log_date = ? ORDER BY id ASC", (log_date,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM workout_log ORDER BY log_date ASC, id ASC"
            ).fetchall()
        return [dict(r) for r in rows]


def get_exercise_names():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT exercise FROM workout_log ORDER BY exercise ASC"
        ).fetchall()
        return [r["exercise"] for r in rows]


def delete_workout_set(set_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM workout_log WHERE id = ?", (set_id,))
