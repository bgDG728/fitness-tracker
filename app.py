from datetime import date, timedelta

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
c1.metric("熱量攝取", f"{total_cal:.0f} kcal", f"{total_cal - profile['target_calories']:+.0f}→{profile['target_calories']:.0f}")
c2.metric("蛋白質", f"{total_protein:.0f} g", f"{total_protein - profile['target_protein_g']:+.0f}→{profile['target_protein_g']:.0f}")
c3.metric("碳水", f"{total_carb:.0f} g", f"{total_carb - profile['target_carb_g']:+.0f}→{profile['target_carb_g']:.0f}")
c4.metric("脂肪", f"{total_fat:.0f} g", f"{total_fat - profile['target_fat_g']:+.0f}→{profile['target_fat_g']:.0f}")

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

# ---- 本週摘要:不是只看單日數字,給一個趨勢感 ----
st.subheader("本週摘要(過去 7 天)")

today_d = date.today()
week_start = today_d - timedelta(days=6)
week_dates = {(week_start + timedelta(days=i)).isoformat() for i in range(7)}

all_foods = db.get_food_log()
all_workouts = db.get_workout_log()
all_weights = db.get_body_weight_log()

week_foods = [f for f in all_foods if f["log_date"] in week_dates]
week_workouts = [w for w in all_workouts if w["log_date"] in week_dates]

logged_days = {f["log_date"] for f in week_foods} | {w["log_date"] for w in week_workouts}

# 有紀錄的天數才拿來算平均熱量,避免忘記記錄的日子把平均拉低失真
cal_by_day: dict[str, float] = {}
for f in week_foods:
    cal_by_day[f["log_date"]] = cal_by_day.get(f["log_date"], 0) + f["calories"]
avg_cal = sum(cal_by_day.values()) / len(cal_by_day) if cal_by_day else 0

week_volume = sum(w["reps"] * w["weight_kg"] for w in week_workouts)

week_weights = sorted(
    [w for w in all_weights if w["log_date"] in week_dates],
    key=lambda w: w["log_date"],
)
weight_change = (week_weights[-1]["weight_kg"] - week_weights[0]["weight_kg"]) if len(week_weights) >= 2 else None

# 連續記錄天數(從今天往回算,中斷就停)
streak = 0
cursor = today_d
all_logged_dates = {f["log_date"] for f in all_foods} | {w["log_date"] for w in all_workouts}
while cursor.isoformat() in all_logged_dates:
    streak += 1
    cursor -= timedelta(days=1)

wc1, wc2, wc3, wc4 = st.columns(4)
wc1.metric("本週記錄天數", f"{len(logged_days)} / 7 天")
wc2.metric("平均每日熱量", f"{avg_cal:.0f} kcal" if cal_by_day else "—")
wc3.metric("本週總訓練量", f"{week_volume:.0f} kg")
wc4.metric(
    "體重變化",
    f"{weight_change:+.1f} kg" if weight_change is not None else "—",
    help="需要本週內至少 2 筆體重紀錄才會顯示",
)

if streak >= 2:
    st.success(f"🔥 連續記錄 {streak} 天,保持下去!")

st.divider()
st.caption("左側選單:個人設定 / 飲食紀錄 / 訓練紀錄 / 進度圖表")
