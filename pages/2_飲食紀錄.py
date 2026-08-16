import hashlib
import io
from datetime import date, datetime

import pandas as pd
import streamlit as st
from PIL import Image
from streamlit_cropper import st_cropper

import coach
import db
import food_db
import food_parser
import food_vision

db.init_db()

st.set_page_config(page_title="飲食紀錄", page_icon="🍚")
st.title("🍚 飲食紀錄")

profile = db.get_profile()
if not profile:
    st.warning("還沒有設定目標熱量,建議先去「個人設定」頁面填一次基本資料。")

selected_date = st.date_input("日期", value=date.today())
log_date = selected_date.isoformat()


def _guess_meal_type():
    """依現在時間猜一個預設餐別,練前/練後餐無法用時間判斷,使用者可自行改選。"""
    hour = datetime.now().hour
    if hour < 10:
        return "早餐"
    if hour < 15:
        return "午餐"
    return "晚餐"


# ---- 快速輸入:一次貼上多樣食物,自動比對資料庫、換算份量 ----
with st.expander("⚡ 快速輸入(一次貼上多樣食物)", expanded=False):
    st.caption(
        "一行一項,格式是「克數+品名」,順序、中間空格都可以,例如「300白飯」「75 透抽」。"
        "解析後會自動比對資料庫抓最接近的品項換算營養素;比對錯誤或查無資料的項目,"
        "可以在預覽時手動改選候選或選略過,按「確認加入」才會真的寫進紀錄。"
    )
    quick_food_text = st.text_area(
        "貼上文字", height=150, key="quick_food_input_text",
        placeholder="300白飯\n100菜\n75肉\n75 透抽\n150豆乾",
    )
    if st.button("解析", key="parse_quick_food"):
        parsed_items = food_parser.parse_quick_food_input(quick_food_text)
        if not parsed_items:
            st.warning("沒解析出任何資料,檢查一下格式(每行「克數+品名」)。")
            st.session_state.pop("quick_food_parsed", None)
        else:
            st.session_state["quick_food_parsed"] = [
                {
                    "輸入": f"{item.grams:.0f}g {item.query}",
                    "克數": item.grams,
                    "候選": food_db.search_food(item.query, limit=5),
                }
                for item in parsed_items
            ]

    parsed_rows = st.session_state.get("quick_food_parsed")
    if parsed_rows:
        st.write("解析預覽:")
        for i, row in enumerate(parsed_rows):
            with st.container(border=True):
                cols = st.columns([2, 1, 2])
                cols[0].markdown(f"**{row['輸入']}**")
                grams = cols[1].number_input(
                    "克數", min_value=1.0, value=float(row["克數"]), step=10.0,
                    key=f"quick_food_grams_{i}", label_visibility="collapsed",
                )
                options = [c["name"] for c in row["候選"]] + ["（略過)"]
                choice = cols[2].selectbox(
                    "比對到的品項", options, index=0,
                    key=f"quick_food_choice_{i}", label_visibility="collapsed",
                )
                row["grams_input"] = grams
                row["choice"] = choice
                if choice != "（略過)":
                    matched = next(c for c in row["候選"] if c["name"] == choice)
                    ratio = grams / 100
                    row["matched"] = matched
                    st.caption(
                        f"換算:{matched['calories_per_100g'] * ratio:.0f} kcal ・ "
                        f"蛋白質 {matched['protein_per_100g'] * ratio:.1f}g ・ "
                        f"碳水 {matched['carb_per_100g'] * ratio:.1f}g ・ "
                        f"脂肪 {matched['fat_per_100g'] * ratio:.1f}g"
                    )
                else:
                    st.caption("查無資料或選擇略過,確認加入時不會匯入這筆,可到下面表單手動輸入。")

        quick_meal_type = st.selectbox(
            "這批要記到哪個餐別", db.MEAL_TYPES,
            index=db.MEAL_TYPES.index(_guess_meal_type()), key="quick_food_meal_type",
        )
        if st.button("✅ 確認加入", type="primary", key="confirm_quick_food_import"):
            imported = 0
            for row in parsed_rows:
                if row["choice"] == "（略過)":
                    continue
                matched = row["matched"]
                ratio = row["grams_input"] / 100
                db.add_food(
                    matched["name"],
                    round(matched["calories_per_100g"] * ratio, 1),
                    round(matched["protein_per_100g"] * ratio, 1),
                    round(matched["carb_per_100g"] * ratio, 1),
                    round(matched["fat_per_100g"] * ratio, 1),
                    meal_type=quick_meal_type, log_date=log_date,
                )
                imported += 1
            st.success(f"已加入 {imported} 筆紀錄。")
            del st.session_state["quick_food_parsed"]
            st.rerun()

st.divider()

# ---- 拍照辨識食物(Chinese-CLIP 零樣本分類,本機免費,僅供輔助確認)----
st.subheader("📷 拍照辨識食物")
st.caption(
    "上傳或拍照食物,自動比對出最相近的候選食品,從中確認選擇——辨識結果僅供輔助,"
    "務必確認選到的是正確的食物。份量預設用 100g 的計算基礎,請自行調整成實際重量。"
)

upload_col, camera_col = st.columns(2)
with upload_col:
    uploaded_photo = st.file_uploader("上傳照片", type=["jpg", "jpeg", "png"], key="food_photo_upload")
with camera_col:
    camera_photo = st.camera_input("或直接拍照", key="food_photo_camera")

image_source = camera_photo or uploaded_photo
if image_source is not None:
    image_bytes = image_source.getvalue()
    photo_hash = hashlib.sha256(image_bytes).hexdigest()
    if st.session_state.get("food_vision_photo_hash") != photo_hash:
        # 換了一張新照片,清掉舊的框選狀態跟辨識結果
        st.session_state["food_vision_photo_hash"] = photo_hash
        st.session_state["food_vision_results"] = []

    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    st.markdown("**框選一個食物再辨識**")
    st.caption(
        "一張照片裡有好幾樣食物時(例如早餐盤裡的麵包、水煮蛋、優格),拖曳/縮放下方框選"
        "範圍只圈住其中一個食物,按「辨識這一框」。確認加入紀錄後,同一張照片可以再框下一個"
        "食物繼續辨識,不用重新拍照或上傳。"
    )
    cropped_image = st_cropper(
        image,
        realtime_update=True,
        box_color="#FF4B4B",
        aspect_ratio=None,
        return_type="image",
        key=f"food_cropper_{photo_hash}",
    )

    preview_col, action_col = st.columns([1, 3])
    with preview_col:
        st.image(cropped_image, caption="目前框選範圍", width="stretch")
    with action_col:
        if st.button("🔍 辨識這一框", type="primary"):
            with st.spinner("辨識中,第一次使用需要先下載模型並建立食品名稱索引,可能要等一下..."):
                try:
                    st.session_state["food_vision_results"] = food_vision.classify_image(cropped_image)
                except Exception as e:
                    st.session_state["food_vision_results"] = []
                    st.error(f"辨識失敗:{e}")

vision_results = st.session_state.get("food_vision_results", [])
if vision_results:
    st.markdown("**辨識候選(選一個確認)**")
    for i, item in enumerate(vision_results):
        with st.container(border=True):
            cols = st.columns([3, 1, 1])
            cols[0].markdown(
                f"**{item['name']}**({item['category']})\n\n"
                f"相似度 {item['score']:.0%} ・ 僅供參考,請確認是否正確"
            )
            grams = cols[1].number_input("份量(g)", min_value=1, value=100, step=10, key=f"vision_grams_{i}")
            if cols[2].button("使用這筆", key=f"vision_use_{i}"):
                food = db.get_tfda_food_by_sample_id(item["sample_id"])
                ratio = grams / 100
                st.session_state["food_prefill_name"] = food["name"]
                st.session_state["food_prefill_calories"] = round(food["calories_per_100g"] * ratio, 1)
                st.session_state["food_prefill_protein"] = round(food["protein_per_100g"] * ratio, 1)
                st.session_state["food_prefill_carb"] = round(food["carb_per_100g"] * ratio, 1)
                st.session_state["food_prefill_fat"] = round(food["fat_per_100g"] * ratio, 1)
                st.session_state["food_vision_results"] = []
                st.rerun()

st.divider()

# ---- 免費食物資料庫搜尋(衛福部食藥署台灣食品營養成分資料庫,本機查詢)----
st.subheader("🔍 搜尋食物資料庫")
st.caption(
    "輸入食物名稱自動帶出每 100g 熱量/營養素,不用自己查營養標示、不用自己算。"
    "資料來自衛福部食藥署官方逐年化驗的台灣食品營養成分資料庫,本機查詢不需要網路。"
)

search_col, btn_col = st.columns([4, 1])
with search_col:
    query = st.text_input("搜尋食物", label_visibility="collapsed", placeholder="例如:白飯、雞胸肉、鯖魚")
with btn_col:
    do_search = st.button("搜尋", width="stretch")

if do_search and query:
    st.session_state["food_search_results"] = food_db.search_food(query)

results = st.session_state.get("food_search_results", [])
if do_search and query and not results:
    st.warning("查無資料,試試英文品名,或直接用下方手動輸入。")

for i, item in enumerate(results):
    with st.container(border=True):
        cols = st.columns([3, 1, 1])
        label = item["name"] + (f"({item['brand']})" if item["brand"] else "")
        cols[0].markdown(
            f"**{label}**\n\n每 100g:{item['calories_per_100g']} kcal ・ "
            f"蛋白質 {item['protein_per_100g']}g ・ 碳水 {item['carb_per_100g']}g ・ 脂肪 {item['fat_per_100g']}g"
        )
        grams = cols[1].number_input("份量(g)", min_value=1, value=100, step=10, key=f"grams_{i}")
        if cols[2].button("使用這筆", key=f"use_{i}"):
            ratio = grams / 100
            st.session_state["food_prefill_name"] = item["name"]
            st.session_state["food_prefill_calories"] = round(item["calories_per_100g"] * ratio, 1)
            st.session_state["food_prefill_protein"] = round(item["protein_per_100g"] * ratio, 1)
            st.session_state["food_prefill_carb"] = round(item["carb_per_100g"] * ratio, 1)
            st.session_state["food_prefill_fat"] = round(item["fat_per_100g"] * ratio, 1)
            st.session_state["food_search_results"] = []
            st.rerun()

# ---- 常用品項:吃過的東西一鍵帶入,不用每次重打 ----
all_foods_history = db.get_food_log()
if all_foods_history:
    freq: dict[str, dict] = {}
    for f in all_foods_history:
        entry = freq.setdefault(f["meal_name"], {"count": 0, "latest": f})
        entry["count"] += 1
        if f["id"] > entry["latest"]["id"]:
            entry["latest"] = f
    top_items = sorted(freq.items(), key=lambda kv: (-kv[1]["count"], -kv[1]["latest"]["id"]))[:8]

    if top_items:
        st.markdown("**常用品項(點一下帶入下方表單)**")
        chip_cols = st.columns(4)
        for idx, (name, info) in enumerate(top_items):
            f = info["latest"]
            with chip_cols[idx % 4]:
                if st.button(f"{name}\n{f['calories']:.0f}kcal", key=f"quick_food_{idx}", width="stretch"):
                    st.session_state["food_prefill_name"] = f["meal_name"]
                    st.session_state["food_prefill_calories"] = f["calories"]
                    st.session_state["food_prefill_protein"] = f["protein_g"]
                    st.session_state["food_prefill_carb"] = f["carb_g"]
                    st.session_state["food_prefill_fat"] = f["fat_g"]
                    st.rerun()

st.divider()

with st.form("food_form", clear_on_submit=True):
    st.subheader("新增一筆")
    meal_type = st.selectbox(
        "餐別/時間點", db.MEAL_TYPES,
        index=db.MEAL_TYPES.index(_guess_meal_type()),
    )
    meal_name = st.text_input("品項名稱", value=st.session_state.get("food_prefill_name", ""), placeholder="例如:雞胸肉便當")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        calories = st.number_input("熱量 (kcal)", min_value=0.0, value=st.session_state.get("food_prefill_calories", 0.0), step=10.0)
    with col2:
        protein_g = st.number_input("蛋白質 (g)", min_value=0.0, value=st.session_state.get("food_prefill_protein", 0.0), step=1.0)
    with col3:
        carb_g = st.number_input("碳水 (g)", min_value=0.0, value=st.session_state.get("food_prefill_carb", 0.0), step=1.0)
    with col4:
        fat_g = st.number_input("脂肪 (g)", min_value=0.0, value=st.session_state.get("food_prefill_fat", 0.0), step=1.0)
    note = st.text_input("備註(選填)")

    st.caption(
        "上面填的營養素如果不是每 100g 的量(例如直接抄營養標示上「每份 240ml」"
        "或「每匙 30g」的數字),請在下面填這份數值實際對應的克數——存入食物"
        "資料庫時會自動除以這個克數、換算成每 100g,下次搜尋才不會抓錯份量。"
        "不確定的話留 100 即可。"
    )
    base_grams = st.number_input(
        "上面數值對應的克數", min_value=1.0, value=100.0, step=10.0,
    )

    btn_col1, btn_col2 = st.columns(2)
    with btn_col1:
        submitted = st.form_submit_button("加入紀錄", type="primary")
    with btn_col2:
        submitted_and_saved = st.form_submit_button("加入紀錄 + 存入食物資料庫")

if submitted or submitted_and_saved:
    if not meal_name:
        st.error("請填品項名稱。")
    else:
        db.add_food(meal_name, calories, protein_g, carb_g, fat_g, note, meal_type=meal_type, log_date=log_date)
        msg = f"已加入:{meal_name}"
        if submitted_and_saved:
            ratio = 100 / base_grams
            db.upsert_tfda_food(
                f"manual_{meal_name}", "自訂", meal_name,
                round(calories * ratio, 2),
                round(protein_g * ratio, 2),
                round(carb_g * ratio, 2),
                round(fat_g * ratio, 2),
                source="manual",
            )
            msg += "(已同步存入食物資料庫,下次可直接搜尋帶入)"
        for k in ["food_prefill_name", "food_prefill_calories", "food_prefill_protein", "food_prefill_carb", "food_prefill_fat"]:
            st.session_state.pop(k, None)
        st.success(msg)
        st.rerun()

st.divider()

foods = db.get_food_log(log_date)
total_cal = sum(f["calories"] for f in foods)
total_protein = sum(f["protein_g"] for f in foods)
total_carb = sum(f["carb_g"] for f in foods)
total_fat = sum(f["fat_g"] for f in foods)

st.subheader(f"{selected_date.isoformat()} 的紀錄")

if profile:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("熱量", f"{total_cal:.0f}", f"{total_cal - profile['target_calories']:+.0f}→{profile['target_calories']:.0f}")
    c2.metric("蛋白質", f"{total_protein:.0f} g", f"{total_protein - profile['target_protein_g']:+.0f}→{profile['target_protein_g']:.0f}")
    c3.metric("碳水", f"{total_carb:.0f} g", f"{total_carb - profile['target_carb_g']:+.0f}→{profile['target_carb_g']:.0f}")
    c4.metric("脂肪", f"{total_fat:.0f} g", f"{total_fat - profile['target_fat_g']:+.0f}→{profile['target_fat_g']:.0f}")

    insights = coach.diet_insight(
        total_cal, profile["target_calories"],
        total_protein, profile["target_protein_g"],
        total_carb, profile["target_carb_g"],
        total_fat, profile["target_fat_g"],
    )
    for tip in insights:
        st.info(f"💡 {tip}")
else:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("熱量", f"{total_cal:.0f}")
    c2.metric("蛋白質", f"{total_protein:.0f} g")
    c3.metric("碳水", f"{total_carb:.0f} g")
    c4.metric("脂肪", f"{total_fat:.0f} g")

if foods:
    groups: dict[str, list] = {mt: [] for mt in db.MEAL_TYPES}
    groups["未分類"] = []
    for f in foods:
        groups.setdefault(f["meal_type"] or "未分類", []).append(f)

    for group_name, items in groups.items():
        if not items:
            continue
        group_cal = sum(i["calories"] for i in items)
        st.markdown(f"**{group_name}** ・ {group_cal:.0f} kcal")
        df = pd.DataFrame(items)[["meal_name", "calories", "protein_g", "carb_g", "fat_g", "note"]]
        df.columns = ["品項", "熱量", "蛋白質(g)", "碳水(g)", "脂肪(g)", "備註"]
        st.dataframe(df, width="stretch", hide_index=True)

    del_options = {f"[{f['meal_type'] or '未分類'}] {f['meal_name']}({f['calories']:.0f} kcal)": f["id"] for f in foods}
    to_delete = st.selectbox("刪除某一筆", ["-"] + list(del_options.keys()))
    if to_delete != "-" and st.button("確認刪除", type="secondary"):
        db.delete_food(del_options[to_delete])
        st.rerun()
else:
    st.info("這天還沒有紀錄。")
