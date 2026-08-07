from datetime import date

import streamlit as st

import db

db.init_db()

st.set_page_config(page_title="健身總覽", page_icon="💪", layout="wide")
st.title("💪 今日總覽")

today = date.today().isoformat()
profile = db.get_profile()

if not profile:
    st.warning("還沒有設定個人資料,請先到左側「個人設定」頁面填寫,才能算出每日熱量目標。")
    st.stop()

foods_today = db.get_food_log(today)
workout_today = db.get_workout_log(today)

total_cal = sum(f["calories"] for f in foods_today)
total_protein = sum(f["protein_g"] for f in foods_today)
total_carb = sum(f["carb_g"] for f in foods_today)
total_fat = sum(f["fat_g"] for f in foods_today)
total_volume = sum(s["reps"] * s["weight_kg"] for s in workout_today)

st.subheader("熱量與營養素(今日)")
c1, c2, c3, c4 = st.columns(4)
c1.metric("熱量攝取", f"{total_cal:.0f} kcal", f"{total_cal - profile['target_calories']:+.0f} 目標 {profile['target_calories']:.0f}")
c2.metric("蛋白質", f"{total_protein:.0f} g", f"{total_protein - profile['target_protein_g']:+.0f} 目標 {profile['target_protein_g']:.0f}")
c3.metric("碳水", f"{total_carb:.0f} g", f"{total_carb - profile['target_carb_g']:+.0f} 目標 {profile['target_carb_g']:.0f}")
c4.metric("脂肪", f"{total_fat:.0f} g", f"{total_fat - profile['target_fat_g']:+.0f} 目標 {profile['target_fat_g']:.0f}")

remaining = profile["target_calories"] - total_cal
if remaining >= 0:
    st.progress(min(total_cal / profile["target_calories"], 1.0), text=f"還可以吃 {remaining:.0f} kcal")
else:
    st.progress(1.0, text=f"已超過目標 {-remaining:.0f} kcal")

st.divider()

st.subheader("訓練(今日)")
if workout_today:
    st.metric("今日總訓練量", f"{total_volume:.0f} kg")
    exercises_today = sorted(set(s["exercise"] for s in workout_today))
    st.write("今天練了:" + "、".join(exercises_today))
else:
    st.info("今天還沒有訓練紀錄。")

st.divider()
st.caption("左側選單:個人設定 / 飲食紀錄 / 訓練紀錄 / 進度圖表")
