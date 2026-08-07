from datetime import date

import pandas as pd
import streamlit as st

import coach
import db
import food_api

db.init_db()

st.set_page_config(page_title="飲食紀錄", page_icon="🍚")
st.title("🍚 飲食紀錄")

profile = db.get_profile()
if not profile:
    st.warning("還沒有設定目標熱量,建議先去「個人設定」頁面填一次基本資料。")

selected_date = st.date_input("日期", value=date.today())
log_date = selected_date.isoformat()

# ---- 免費食物資料庫搜尋(Open Food Facts,不需要 API key)----
st.subheader("🔍 搜尋食物資料庫")
st.caption(
    "輸入食物名稱自動帶出每 100g 熱量/營養素,不用自己查營養標示(英文品名搜尋結果較齊全)。"
    "資料庫由使用者協作維護,已過濾掉明顯不合理的數值,但仍建議挑選看起來合理的品項。"
)

search_col, btn_col = st.columns([4, 1])
with search_col:
    query = st.text_input("搜尋食物", label_visibility="collapsed", placeholder="例如:chicken breast、banana、白飯")
with btn_col:
    do_search = st.button("搜尋", width="stretch")

if do_search and query:
    st.session_state["food_search_results"] = food_api.search_food(query)

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

    submitted = st.form_submit_button("加入紀錄", type="primary")

if submitted:
    if not meal_name:
        st.error("請填品項名稱。")
    else:
        db.add_food(meal_name, calories, protein_g, carb_g, fat_g, note, log_date=log_date)
        for k in ["food_prefill_name", "food_prefill_calories", "food_prefill_protein", "food_prefill_carb", "food_prefill_fat"]:
            st.session_state.pop(k, None)
        st.success(f"已加入:{meal_name}")
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
    df = pd.DataFrame(foods)[["meal_name", "calories", "protein_g", "carb_g", "fat_g", "note"]]
    df.columns = ["品項", "熱量", "蛋白質(g)", "碳水(g)", "脂肪(g)", "備註"]
    st.dataframe(df, width="stretch", hide_index=True)

    del_options = {f"{f['meal_name']}({f['calories']:.0f} kcal)": f["id"] for f in foods}
    to_delete = st.selectbox("刪除某一筆", ["-"] + list(del_options.keys()))
    if to_delete != "-" and st.button("確認刪除", type="secondary"):
        db.delete_food(del_options[to_delete])
        st.rerun()
else:
    st.info("這天還沒有紀錄。")
