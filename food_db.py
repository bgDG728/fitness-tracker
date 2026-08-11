"""
食物資料庫查詢——查本機的台灣食品營養成分資料庫(衛福部食藥署開放資料,
已由 import_tfda.py 匯入 fitness.db 的 tfda_foods 表)。

取代原本的 Open Food Facts 線上查詢:Open Food Facts 是歐美為主的包裝食品
條碼資料庫,查台灣家常菜/在地食材常常查不到或抓到不相關的西式包裝食品。
改成查本機資料庫後,查詢不需要網路、速度更快,資料也是官方逐年化驗的結果。
"""

import db


def search_food(query: str, limit: int = 8) -> list[dict]:
    """
    回傳符合搜尋字串的食物列表,每一筆:
    {name, brand, calories_per_100g, protein_per_100g, carb_per_100g, fat_per_100g}

    brand 欄位沿用舊介面的命名,實際放的是食品分類(例如「魚貝類」),
    在搜尋結果卡片上當作補充資訊顯示。
    """
    if not query.strip():
        return []

    rows = db.search_tfda_foods(query.strip(), limit=limit)
    return [
        {
            "name": row["name"],
            "brand": row["category"] or "",
            "calories_per_100g": row["calories_per_100g"],
            "protein_per_100g": row["protein_per_100g"],
            "carb_per_100g": row["carb_per_100g"],
            "fat_per_100g": row["fat_per_100g"],
        }
        for row in rows
    ]
