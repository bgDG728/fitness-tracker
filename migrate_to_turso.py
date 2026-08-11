"""
一次性遷移腳本:把既有本機 fitness.db(純 sqlite3)裡的資料搬到 Turso。

背景:db.py 改成支援 Turso(libSQL embedded replica)之後,雲端/接了 Turso
的本機都改用另一個檔案(fitness_turso_replica.db,見 db.py 開頭說明),
不會直接沿用舊的 fitness.db —— libsql 的同步機制需要自己管理的中繼資料,
不能把既有的、非 libsql 建立的 sqlite3 檔案直接當成 replica 用。

用法(先在 .streamlit/secrets.toml 或環境變數設好 TURSO_DATABASE_URL /
TURSO_AUTH_TOKEN,確認 db._turso_config() 不是 None 再跑):

    venv\\Scripts\\python.exe migrate_to_turso.py

只搬個人資料(profile / body_weight_log / food_log / workout_log /
exercise_goals);tfda_foods 是唯讀的參考資料庫,同一支腳本也會搬,但如果
之後想重新整理,直接重跑 import_tfda.py / import_usda.py(對著已接上
Turso 的 db.py)重新匯入即可,不一定要靠這支腳本。
"""

import sqlite3
from pathlib import Path

import db

SRC_PATH = Path(__file__).parent / "fitness.db"


def migrate():
    if db._turso_config() is None:
        raise SystemExit(
            "沒有偵測到 TURSO_DATABASE_URL / TURSO_AUTH_TOKEN,"
            "先在 .streamlit/secrets.toml 或環境變數設定好再跑這支腳本。"
        )
    if not SRC_PATH.exists():
        raise SystemExit(f"找不到 {SRC_PATH},沒有資料可以搬。")

    src = sqlite3.connect(SRC_PATH)
    src.row_factory = sqlite3.Row

    db.init_db()

    profile = src.execute("SELECT * FROM profile WHERE id = 1").fetchone()
    if profile:
        db.save_profile(
            profile["height_cm"], profile["age"], profile["sex"],
            profile["activity_level"], profile["goal"],
            profile["target_calories"], profile["target_protein_g"],
            profile["target_carb_g"], profile["target_fat_g"],
        )
        print("profile migrated")

    weights = src.execute("SELECT * FROM body_weight_log ORDER BY id").fetchall()
    for w in weights:
        db.add_body_weight(w["weight_kg"], log_date=w["log_date"])
    print(f"{len(weights)} body_weight_log rows migrated")

    foods = src.execute("SELECT * FROM food_log ORDER BY id").fetchall()
    for f in foods:
        db.add_food(
            f["meal_name"], f["calories"], f["protein_g"], f["carb_g"], f["fat_g"],
            note=f["note"] or "", meal_type=f["meal_type"] or "", log_date=f["log_date"],
        )
    print(f"{len(foods)} food_log rows migrated")

    workouts = src.execute("SELECT * FROM workout_log ORDER BY id").fetchall()
    for w in workouts:
        db.add_workout_set(
            w["exercise"], w["set_number"], w["reps"], w["weight_kg"],
            note=w["note"] or "", equipment=w["equipment"] or "", log_date=w["log_date"],
        )
    print(f"{len(workouts)} workout_log rows migrated")

    goals = src.execute("SELECT * FROM exercise_goals").fetchall()
    for g in goals:
        db.set_exercise_goal(g["exercise"], g["goal"])
    print(f"{len(goals)} exercise_goals rows migrated")

    tfda_rows = src.execute(
        "SELECT sample_id, category, name, calories_per_100g, protein_per_100g, "
        "carb_per_100g, fat_per_100g, source FROM tfda_foods"
    ).fetchall()
    by_source: dict[str, list[tuple]] = {}
    for r in tfda_rows:
        by_source.setdefault(r["source"], []).append((
            r["sample_id"], r["category"], r["name"],
            r["calories_per_100g"], r["protein_per_100g"], r["carb_per_100g"], r["fat_per_100g"],
        ))
    for source, rows in by_source.items():
        db.replace_tfda_foods(rows, source=source)
        print(f"{len(rows)} tfda_foods rows migrated (source={source})")

    src.close()
    print("MIGRATION DONE")


if __name__ == "__main__":
    migrate()
