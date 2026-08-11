"""
健身飲食訓練紀錄系統的資料庫層。用 SQLite,單一使用者、本機檔案儲存
(fitness.db),不需要額外架設資料庫伺服器。

雲端部署(Streamlit Community Cloud)時檔案系統不持久,重新部署/休眠喚醒
會遺失資料,所以額外支援 Turso(libSQL)embedded replica 模式:讀寫都呼叫
conn.sync() 跟遠端 Turso 資料庫同步。有沒有設定 TURSO_DATABASE_URL /
TURSO_AUTH_TOKEN(環境變數或 .streamlit/secrets.toml)決定要不要啟用這個
模式,沒設定就是單純本機 sqlite3(DB_PATH),本機開發不受影響、不用強制
每次都連線 Turso。

注意:libsql 的 embedded replica 需要自己管理本機檔案的同步中繼資料
(sync generation/frame number),不能直接拿一個既有的、非 libsql 建立的
sqlite3 檔案來用(會噴 "db file exists but metadata file does not")。
所以 Turso 模式用另一個檔名(TURSO_REPLICA_PATH),不會跟純本機模式共用
同一個檔案。既有 fitness.db 裡的資料要接上 Turso,需要跑一次
migrate_to_turso.py(見 README「線上使用」)。
"""

import os
import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path

DB_PATH = Path(__file__).parent / "fitness.db"
TURSO_REPLICA_PATH = Path(__file__).parent / "fitness_turso_replica.db"


def _turso_config():
    url = os.environ.get("TURSO_DATABASE_URL")
    token = os.environ.get("TURSO_AUTH_TOKEN")
    if not url or not token:
        try:
            import streamlit as st
            url = url or st.secrets.get("TURSO_DATABASE_URL")
            token = token or st.secrets.get("TURSO_AUTH_TOKEN")
        except Exception:
            pass
    return (url, token) if url and token else None


class _Row:
    """模仿 sqlite3.Row:同時支援 row["欄位名"]、row[0](位置索引)、
    dict(row) 三種用法,因為 db.py 三種都有用到。"""

    __slots__ = ("_data",)

    def __init__(self, columns, values):
        self._data = dict(zip(columns, values))

    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self._data.values())[key]
        return self._data[key]

    def keys(self):
        return self._data.keys()


class _DictCursor:
    """libsql 的 Cursor 回傳的每一列是原始 tuple,沒有欄位名稱可查,也不能
    像 sqlite3.Cursor 一樣直接被 for 迴圈疊代。這裡把每一列包成 _Row(用
    cursor.description 拿欄位名稱),讓 db.py 其他地方寫的 dict(row)、
    row["欄位名"]、row[0]、for row in conn.execute(...) 在兩種連線模式下
    可以用同一套程式碼。"""

    def __init__(self, cursor):
        self._cursor = cursor
        self._columns = [d[0] for d in cursor.description] if cursor.description else []

    def _to_row(self, values):
        return _Row(self._columns, values) if values is not None else None

    def fetchone(self):
        return self._to_row(self._cursor.fetchone())

    def fetchall(self):
        return [self._to_row(v) for v in self._cursor.fetchall()]

    def __iter__(self):
        return iter(self.fetchall())


class _TursoConn:
    """把 libsql 連線包成跟 sqlite3.Connection 同樣的呼叫介面(execute /
    executemany / executescript / commit / close),讓 get_conn() 的呼叫端
    (db.py 其餘所有函式)不用分兩套寫法。"""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=()):
        return _DictCursor(self._conn.execute(sql, params))

    def executemany(self, sql, seq):
        return self._conn.executemany(sql, seq)

    def executescript(self, script):
        return self._conn.executescript(script)

    def commit(self):
        self._conn.commit()

    def sync(self):
        self._conn.sync()

    def close(self):
        self._conn.close()


MEAL_TYPES = ["早餐", "午餐", "晚餐", "練前餐", "練後餐"]

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
    note TEXT,
    meal_type TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS workout_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    log_date TEXT NOT NULL,
    exercise TEXT NOT NULL,
    set_number INTEGER NOT NULL,
    reps INTEGER NOT NULL,
    weight_kg REAL NOT NULL,
    note TEXT,
    equipment TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS exercise_goals (
    exercise TEXT PRIMARY KEY,
    goal TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tfda_foods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_id TEXT UNIQUE NOT NULL,
    category TEXT,
    name TEXT NOT NULL,
    calories_per_100g REAL NOT NULL,
    protein_per_100g REAL NOT NULL,
    carb_per_100g REAL NOT NULL,
    fat_per_100g REAL NOT NULL,
    source TEXT DEFAULT 'tfda'
);
CREATE INDEX IF NOT EXISTS idx_tfda_foods_name ON tfda_foods(name);
"""


@contextmanager
def get_conn():
    turso = _turso_config()
    if turso:
        import libsql
        url, token = turso
        raw = libsql.connect(str(TURSO_REPLICA_PATH), sync_url=url, auth_token=token)
        raw.sync()
        conn = _TursoConn(raw)
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
        if turso:
            raw.sync()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        # 舊版 fitness.db 沒有 meal_type 欄位,補一次 migration(既有資料留空,
        # 會歸類到「未分類」,不影響過去的紀錄)
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(food_log)")}
        if "meal_type" not in columns:
            conn.execute("ALTER TABLE food_log ADD COLUMN meal_type TEXT DEFAULT ''")

        # 舊版 fitness.db 沒有 source 欄位,補一次 migration(既有資料都是
        # import_tfda.py 匯入的,補上後預設值 'tfda' 剛好正確,不用額外回填)
        food_columns = {row["name"] for row in conn.execute("PRAGMA table_info(tfda_foods)")}
        if "source" not in food_columns:
            conn.execute("ALTER TABLE tfda_foods ADD COLUMN source TEXT DEFAULT 'tfda'")

        # 舊版 fitness.db 沒有 equipment 欄位,補一次 migration(既有資料留空,
        # 不影響過去的紀錄,PR/教練建議照樣可以算,只是沒有器材分類資訊)
        workout_columns = {row["name"] for row in conn.execute("PRAGMA table_info(workout_log)")}
        if "equipment" not in workout_columns:
            conn.execute("ALTER TABLE workout_log ADD COLUMN equipment TEXT DEFAULT ''")


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

def add_food(meal_name, calories, protein_g, carb_g, fat_g, note="", meal_type="", log_date=None):
    log_date = log_date or date.today().isoformat()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO food_log (log_date, meal_name, calories, protein_g, carb_g, fat_g, note, meal_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (log_date, meal_name, calories, protein_g, carb_g, fat_g, note, meal_type),
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

def add_workout_set(exercise, set_number, reps, weight_kg, note="", equipment="", log_date=None):
    log_date = log_date or date.today().isoformat()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO workout_log (log_date, exercise, set_number, reps, weight_kg, note, equipment)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (log_date, exercise, set_number, reps, weight_kg, note, equipment),
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


# ---- exercise goals(訓練目標,例如最大力量/肌肥大/肌耐力,依動作分開設定)----

def get_exercise_goal(exercise):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT goal FROM exercise_goals WHERE exercise = ?", (exercise,)
        ).fetchone()
        return row["goal"] if row else None


def set_exercise_goal(exercise, goal):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO exercise_goals (exercise, goal) VALUES (?, ?)
            ON CONFLICT(exercise) DO UPDATE SET goal=excluded.goal
            """,
            (exercise, goal),
        )


def get_all_exercise_goals():
    with get_conn() as conn:
        rows = conn.execute("SELECT exercise, goal FROM exercise_goals").fetchall()
        return {r["exercise"]: r["goal"] for r in rows}


# ---- 台灣食品營養成分資料庫(tfda_foods)----

def replace_tfda_foods(rows, source="tfda"):
    """
    rows: iterable of (sample_id, category, name, calories, protein, carb, fat)。
    每次匯入只取代同一個 source 的舊資料(例如重跑 import_tfda.py 只會換掉
    source='tfda' 的資料,不會動到 import_usda.py 補進來的 source='usda'
    資料,反之亦然)。
    """
    rows_with_source = [tuple(row) + (source,) for row in rows]
    with get_conn() as conn:
        conn.execute("DELETE FROM tfda_foods WHERE source = ?", (source,))
        conn.executemany(
            """
            INSERT INTO tfda_foods
                (sample_id, category, name, calories_per_100g, protein_per_100g, carb_per_100g, fat_per_100g, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows_with_source,
        )


def upsert_tfda_food(sample_id, category, name, calories, protein, carb, fat, source):
    """
    新增或更新單一筆食品(以 sample_id 為準)。給像 import_usda.py 這種
    一次查一筆外部 API 的匯入方式用——每查到一筆就直接寫入,即使中途因為
    API 速率限制被打斷,已經查到的資料也不會遺失,重跑時可以接著補。
    """
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO tfda_foods
                (sample_id, category, name, calories_per_100g, protein_per_100g, carb_per_100g, fat_per_100g, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(sample_id) DO UPDATE SET
                category=excluded.category,
                name=excluded.name,
                calories_per_100g=excluded.calories_per_100g,
                protein_per_100g=excluded.protein_per_100g,
                carb_per_100g=excluded.carb_per_100g,
                fat_per_100g=excluded.fat_per_100g,
                source=excluded.source
            """,
            (sample_id, category, name, calories, protein, carb, fat, source),
        )


def get_tfda_foods_by_source(source):
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM tfda_foods WHERE source = ?", (source,)).fetchall()
        return [dict(r) for r in rows]


def get_tfda_food_count():
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM tfda_foods").fetchone()[0]


def search_tfda_foods(query, limit=8):
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM tfda_foods
            WHERE name LIKE ?
            ORDER BY LENGTH(name) ASC
            LIMIT ?
            """,
            (f"%{query}%", limit),
        ).fetchall()
        return [dict(r) for r in rows]


def get_all_tfda_food_names():
    with get_conn() as conn:
        rows = conn.execute("SELECT sample_id, name, category FROM tfda_foods").fetchall()
        return [dict(r) for r in rows]


def get_tfda_food_by_sample_id(sample_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM tfda_foods WHERE sample_id = ?", (sample_id,)
        ).fetchone()
        return dict(row) if row else None
