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


def _is_plausible(calories: float, protein: float, carb: float, fat: float) -> bool:
    """
    Open Food Facts 是群眾協作資料庫,偶爾會出現亂填/打錯的離譜資料
    (曾實測「牛奶」搜尋第一筆是熱量 12.5kcal 但蛋白質/碳水/脂肪都寫 125g,
    三個巨量營養素換算起來要 2000+ kcal,跟標示熱量對不上,明顯是壞資料)。
    這裡用基本物理常識過濾掉不合理的筆數,不盲目相信 API 回傳的每一筆。
    """
    # 每 100g 食物裡,單一巨量營養素不可能超過 100g
    if protein > 100 or carb > 100 or fat > 100:
        return False
    if calories < 0 or calories > 900:  # 900 大約是純脂肪(100g * 9kcal/g)的上限
        return False

    computed = protein * 4 + carb * 4 + fat * 9
    if computed > 0:
        relative_error = abs(calories - computed) / computed
        # 容許一定誤差(標示熱量常有四捨五入、膳食纖維算法不同等落差),
        # 但誤差過大代表資料本身有問題,不是正常的計算落差。
        if relative_error > 0.5 and abs(calories - computed) > 50:
            return False

    return True


def search_food(query: str, limit: int = 8) -> list[dict]:
    """
    回傳符合搜尋字串的食物列表,每一筆:
    {name, brand, calories_per_100g, protein_per_100g, carb_per_100g, fat_per_100g}

    找不到資料、網路有問題,或篩掉不合理資料後沒有結果,都會回傳空 list,
    不會丟例外讓整個頁面壞掉。
    """
    if not query.strip():
        return []

    # 多抓一些筆數,因為過濾掉不合理資料後可能會少於要求的 limit。
    params = {"q": query, "page_size": min(limit * 3, 30)}

    try:
        resp = requests.get(SEARCH_URL, params=params, headers=HEADERS, timeout=TIMEOUT_SECONDS)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError):
        return []

    results = []
    for product in data.get("hits", []):
        if len(results) >= limit:
            break

        nutriments = product.get("nutriments") or {}
        name = product.get("product_name") or product.get("product_name_en")
        if not name:
            continue

        calories = nutriments.get("energy-kcal_100g")
        if calories is None:
            continue

        protein = round(nutriments.get("proteins_100g", 0) or 0, 1)
        carb = round(nutriments.get("carbohydrates_100g", 0) or 0, 1)
        fat = round(nutriments.get("fat_100g", 0) or 0, 1)
        calories = round(calories, 1)

        if not _is_plausible(calories, protein, carb, fat):
            continue

        brands = product.get("brands", "")
        if isinstance(brands, list):
            brands = ", ".join(brands)

        results.append({
            "name": name,
            "brand": brands,
            "calories_per_100g": calories,
            "protein_per_100g": protein,
            "carb_per_100g": carb,
            "fat_per_100g": fat,
        })

    return results
