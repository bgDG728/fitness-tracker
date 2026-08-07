from datetime import date

import pandas as pd
import streamlit as st

import coach
import db

db.init_db()

st.set_page_config(page_title="飲食紀錄", page_icon="🍚")
st.title("🍚 飲食紀錄")

profile = db.get_profile()
if not profile:
    st.warning("還沒有設定目標熱量,建議先去「個人設定」頁面填一次基本資料。")

selected_date = st.date_input("日期", value=date.today())
log_date = selected_date.isoformat()

with st.form("food_form", clear_on_submit=True):
    st.subheader("新增一筆")
    meal_name = st.text_input("品項名稱", placeholder="例如:雞胸肉便當")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        calories = st.number_input("熱量 (kcal)", min_value=0.0, step=10.0)
    with col2:
        protein_g = st.number_input("蛋白質 (g)", min_value=0.0, step=1.0)
    with col3:
        carb_g = st.number_input("碳水 (g)", min_value=0.0, step=1.0)
    with col4:
        fat_g = st.number_input("脂肪 (g)", min_value=0.0, step=1.0)
    note = st.text_input("備註(選填)")

    submitted = st.form_submit_button("加入紀錄", type="primary")

if submitted:
    if not meal_name:
        st.error("請填品項名稱。")
    else:
        db.add_food(meal_name, calories, protein_g, carb_g, fat_g, note, log_date=log_date)
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
    c1.metric("熱量", f"{total_cal:.0f}", f"{total_cal - profile['target_calories']:+.0f} / 目標 {profile['target_calories']:.0f}")
    c2.metric("蛋白質", f"{total_protein:.0f} g", f"{total_protein - profile['target_protein_g']:+.0f} / 目標 {profile['target_protein_g']:.0f}")
    c3.metric("碳水", f"{total_carb:.0f} g", f"{total_carb - profile['target_carb_g']:+.0f} / 目標 {profile['target_carb_g']:.0f}")
    c4.metric("脂肪", f"{total_fat:.0f} g", f"{total_fat - profile['target_fat_g']:+.0f} / 目標 {profile['target_fat_g']:.0f}")

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
