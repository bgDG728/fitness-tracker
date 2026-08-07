"""
免費食物資料庫查詢(Open Food Facts,不需要 API key)。

讓使用者可以直接搜尋食物名稱,自動帶出每 100g 的熱量/三大營養素,
不用自己查營養標示、自己算,同時完全免費、不需要任何帳號或金鑰。
"""

import requests

# Open Food Facts 的舊版 /cgi/search.pl 已經停用(改回 503)。
# 官方目前建議的全文搜尋是 Search-a-licious(Elasticsearch 服務),
# 一樣完全免費、不需要任何帳號或金鑰。
SEARCH_URL = "https://search.openfoodfacts.org/search"
TIMEOUT_SECONDS = 6
HEADERS = {"User-Agent": "FitnessTrackerPersonalApp/1.0 (local personal use)"}


def search_food(query: str, limit: int = 8) -> list[dict]:
    """
    回傳符合搜尋字串的食物列表,每一筆:
    {name, brand, calories_per_100g, protein_per_100g, carb_per_100g, fat_per_100g}

    找不到資料或網路有問題時回傳空 list,不會丟例外讓整個頁面壞掉。
    """
    if not query.strip():
        return []

    params = {"q": query, "page_size": limit}

    try:
        resp = requests.get(SEARCH_URL, params=params, headers=HEADERS, timeout=TIMEOUT_SECONDS)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError):
        return []

    results = []
    for product in data.get("hits", []):
        nutriments = product.get("nutriments") or {}
        name = product.get("product_name") or product.get("product_name_en")
        if not name:
            continue

        calories = nutriments.get("energy-kcal_100g")
        if calories is None:
            continue

        brands = product.get("brands", "")
        if isinstance(brands, list):
            brands = ", ".join(brands)

        results.append({
            "name": name,
            "brand": brands,
            "calories_per_100g": round(calories, 1),
            "protein_per_100g": round(nutriments.get("proteins_100g", 0) or 0, 1),
            "carb_per_100g": round(nutriments.get("carbohydrates_100g", 0) or 0, 1),
            "fat_per_100g": round(nutriments.get("fat_100g", 0) or 0, 1),
        })

    return results
