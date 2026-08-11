"""
一次性匯入腳本:下載衛福部食藥署「台灣地區食品營養成分資料庫」開放資料,
取代原本的 Open Food Facts 查詢來源。

原因:Open Food Facts 是歐美為主的包裝食品條碼資料庫,查台灣家常菜/在地食材
常常查不到或抓到不相關的西式包裝食品。衛福部資料庫是官方逐年化驗建立的資料,
涵蓋 18 大類食品(魚貝類/肉類/蔬菜類/穀物類/加工調理食品等),對台灣使用者
準確度高很多。免費開放下載,不需要任何帳號或金鑰。

資料集:https://data.gov.tw/dataset/8543
原始資料是「長格式」——同一份食品樣本,每一項營養分析各佔一列(整合編號當
主鍵)。這裡只挑「一般成分」分類底下的熱量/粗蛋白/粗脂肪/總碳水化合物 4 項,
pivot 成一列一個食品的寬格式,寫進 fitness.db 的 tfda_foods 表。

用法:
    venv\\Scripts\\python.exe import_tfda.py

會下載約 4MB 的 zip(解壓後約 128MB JSON),處理後只留下有完整 4 項營養素
的食品(實測約 2000 多筆),原始 JSON 不會留在專案裡。
"""

import io
import json
import zipfile

import requests

import db

SOURCE_URL = "https://data.fda.gov.tw/opendata/exportDataList.do?method=ExportData&InfoId=20&logType=5"
TIMEOUT_SECONDS = 60

# 對應到 tfda_foods 欄位的目標分析項(都屬於「一般成分」分類)
TARGET_ITEMS = {
    "熱量": "calories",
    "粗蛋白": "protein",
    "總碳水化合物": "carb",
    "粗脂肪": "fat",
}


def _parse_number(raw):
    if raw is None:
        return None
    try:
        return float(str(raw).strip())
    except ValueError:
        return None


def fetch_raw_rows():
    print(f"下載中:{SOURCE_URL}")
    resp = requests.get(SOURCE_URL, timeout=TIMEOUT_SECONDS)
    resp.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        json_name = next(name for name in zf.namelist() if name.endswith(".json"))
        with zf.open(json_name) as f:
            return json.load(f)


def pivot_to_foods(raw_rows):
    pivot: dict[str, dict] = {}
    meta: dict[str, tuple[str, str]] = {}  # sample_id -> (name, category)

    for row in raw_rows:
        item = row.get("分析項")
        if row.get("分析項分類") != "一般成分" or item not in TARGET_ITEMS:
            continue

        value = _parse_number(row.get("每100克含量"))
        if value is None:
            continue

        sample_id = row.get("整合編號")
        name = row.get("樣品名稱")
        if not sample_id or not name:
            continue

        pivot.setdefault(sample_id, {})[TARGET_ITEMS[item]] = value
        meta[sample_id] = (name.strip(), row.get("食品分類") or "")

    foods = []
    for sample_id, nutrients in pivot.items():
        if len(nutrients) != 4:
            continue  # 只留下 4 項營養素都齊全的食品,不做半套的插補/猜測
        name, category = meta[sample_id]
        foods.append((
            sample_id,
            category,
            name,
            nutrients["calories"],
            nutrients["protein"],
            nutrients["carb"],
            nutrients["fat"],
        ))
    return foods


def main():
    raw_rows = fetch_raw_rows()
    print(f"原始資料筆數(長格式,每列是一個食品的一項營養分析):{len(raw_rows)}")

    foods = pivot_to_foods(raw_rows)
    print(f"整理出營養素齊全的食品筆數:{len(foods)}")

    db.init_db()
    db.replace_tfda_foods(foods, source="tfda")
    print(f"已寫入 fitness.db 的 tfda_foods 表,共 {db.get_tfda_food_count()} 筆。")


if __name__ == "__main__":
    main()
