"""
一次性匯入腳本:用 USDA FoodData Central(美國農業部,官方免費資料庫,不需要
付費、公開資料)補齊衛福部食藥署資料庫(import_tfda.py)缺乏的西式常見食物,
寫進同一個 fitness.db 的 tfda_foods 表(source='usda',跟 source='tfda' 的
資料分開管理,重跑任一支匯入腳本不會互相覆蓋)。

背景:實測搜尋 tfda_foods,「吐司」「優格」「貝果」「希臘優格」「鮮奶油」
「格蘭諾拉」都是 0 筆——TFDA 資料庫涵蓋台灣家常菜/在地食材很完整,但西式
早餐/輕食常見品項幾乎查不到。USDA FoodData Central 是美國政府另一套官方
逐年化驗資料庫,公信力跟 TFDA 同等級,這裡用的 SR Legacy/Foundation 兩個
資料集也是每 100g 為基礎,跟 TFDA 資料格式一致,不用另外換算。

只挑一份固定清單,不是整包資料庫倒進來——USDA 完整資料庫有上百萬筆包裝
食品,倒進來對這個專案沒有意義,反而會拖慢拍照辨識(food_vision.py)的
零樣本比對品質:候選食品清單越乾淨,比對出來的 Top 3 才越準。清單是從
「TFDA 查不到/查不到乾淨結果」的西式日常食物裡篩的(吐司、貝果、優格、
起司、鮮奶油、義大利麵條等),不含 TFDA 已經有涵蓋的品項(例如培根、香腸、
漢堡包、沙拉醬、酪梨、燕麥片、披薩、火腿——這些查得到就不重複匯入)。

用法:
    venv\\Scripts\\python.exe import_usda.py

免費 API,不需要付費、不需要信用卡。預設用官方共用的 DEMO_KEY(有速率限制,
約 30 次/小時,這份清單一次跑得完)。如果之後想擴充清單常態更新,建議到
https://fdc.nal.usda.gov/api-key-signup 免費申請個人 API key(幾秒鐘完成),
用環境變數 USDA_API_KEY 覆蓋預設值即可。
"""

import os
import time

import requests

import db

API_KEY = os.environ.get("USDA_API_KEY", "DEMO_KEY")
SEARCH_URL = "https://api.nal.usda.gov/fdc/v1/foods/search"
TIMEOUT_SECONDS = 30
REQUEST_INTERVAL_SECONDS = 1.5  # 避免共用 DEMO_KEY 觸發速率限制

# USDA 官方資料集用「營養素編號」(nutrientNumber)識別項目,對應到
# tfda_foods 的四個核心欄位(跟 import_tfda.py 挑的「一般成分」四項一致)
NUTRIENT_NUMBERS = {
    "208": "calories",  # Energy (kcal)
    "203": "protein",   # Protein
    "205": "carb",       # Carbohydrate, by difference
    "204": "fat",         # Total lipid (fat)
}

# 中文品名 -> USDA 查詢字串。只挑 TFDA 資料庫查不到、但日常生活常吃到的
# 西式主食/輕食(早餐吐司類、優格、起司、義大利麵、鮮奶油等)
QUERIES = {
    "白吐司": "bread white",
    "全麥吐司": "bread whole wheat commercially prepared",
    "裸麥麵包": "bread rye",
    "法國麵包": "bread french or vienna",
    "貝果": "bagel plain enriched",
    "英式馬芬": "english muffin plain",
    "原味優格": "yogurt plain whole milk",
    "希臘優格(原味)": "yogurt greek plain",
    "低脂優格": "yogurt plain low fat",
    "茅屋起司": "cheese cottage",
    "奶油乳酪": "cheese cream",
    "切達起司": "cheese cheddar",
    "莫札瑞拉起司": "cheese mozzarella whole milk",
    "帕瑪森起司": "cheese parmesan",
    "玉米穀片": "cereals corn flakes",
    "格蘭諾拉麥片": "granola homemade",
    "義大利麵(熟)": "pasta cooked enriched",
    "鮮奶油": "cream heavy whipping",
    "酸奶油": "sour cream",
}


def _search_one(query: str) -> dict | None:
    resp = requests.get(
        SEARCH_URL,
        params={
            "api_key": API_KEY,
            "query": query,
            "dataType": "SR Legacy,Foundation",
            "pageSize": 1,
        },
        timeout=TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    foods = resp.json().get("foods") or []
    return foods[0] if foods else None


def _extract_nutrients(food: dict) -> dict | None:
    nutrients = {}
    for n in food.get("foodNutrients", []):
        key = NUTRIENT_NUMBERS.get(n.get("nutrientNumber"))
        if key and n.get("value") is not None:
            nutrients[key] = n["value"]
    if len(nutrients) != 4:
        return None  # 四項營養素沒有齊全就跳過,不做半套的插補/猜測
    return nutrients


def main():
    db.init_db()
    # 每查到一筆就直接寫入(upsert),不是查完整份清單才一次寫入——這樣即使
    # 中途被 API 速率限制打斷,已經查到的也不會遺失,重跑時會自動跳過已經
    # 匯入過的品項,只補還沒查到的
    already_done = {f["name"] for f in db.get_tfda_foods_by_source("usda")}
    remaining = {k: v for k, v in QUERIES.items() if k not in already_done}
    if already_done:
        print(f"已經匯入過 {len(already_done)} 筆,這次只補剩下 {len(remaining)} 筆。")

    done_count = 0
    for i, (name_zh, query) in enumerate(remaining.items()):
        if i > 0:
            time.sleep(REQUEST_INTERVAL_SECONDS)
        try:
            food = _search_one(query)
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 429:
                print(
                    f"觸發 USDA 共用 DEMO_KEY 的速率限制,先在這裡停下來"
                    f"(還剩 {len(remaining) - i} 筆沒查)。"
                    f"可以晚點(通常約 1 小時後額度會重置)重跑同一支腳本,"
                    f"會自動接著補剩下的;或到 "
                    f"https://fdc.nal.usda.gov/api-key-signup 免費申請個人"
                    f" API key,用環境變數 USDA_API_KEY 帶入就不會共用額度。"
                )
                break
            print(f"跳過「{name_zh}」:查詢失敗({e})")
            continue
        except requests.RequestException as e:
            print(f"跳過「{name_zh}」:查詢失敗({e})")
            continue

        if not food:
            print(f"跳過「{name_zh}」:USDA 查無結果")
            continue
        nutrients = _extract_nutrients(food)
        if not nutrients:
            print(f"跳過「{name_zh}」:營養素不齊全")
            continue

        sample_id = f"usda_{food['fdcId']}"
        db.upsert_tfda_food(
            sample_id, "西式(USDA)", name_zh,
            nutrients["calories"], nutrients["protein"], nutrients["carb"], nutrients["fat"],
            source="usda",
        )
        done_count += 1
        print(f"{name_zh} <- {food['description']}({nutrients['calories']:.0f} kcal/100g)")

    total_usda = db.get_tfda_food_count()
    print(f"這次新匯入/更新 {done_count} 筆,tfda_foods 現在共 {total_usda} 筆。")


if __name__ == "__main__":
    main()
