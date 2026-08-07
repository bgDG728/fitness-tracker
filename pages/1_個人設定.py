import streamlit as st

import calc
import db

db.init_db()

st.set_page_config(page_title="個人設定", page_icon="⚙️")
st.title("⚙️ 個人設定")
st.caption("填一次基本資料,系統會用 Mifflin-St Jeor 公式幫你算出每日熱量與三大營養素目標。")

profile = db.get_profile()
latest_weight = db.get_latest_body_weight()
default_weight = latest_weight["weight_kg"] if latest_weight else 65.0

with st.form("profile_form"):
    col1, col2 = st.columns(2)
    with col1:
        weight_kg = st.number_input("目前體重 (kg)", min_value=30.0, max_value=200.0,
                                     value=float(default_weight), step=0.1)
        height_cm = st.number_input("身高 (cm)", min_value=120.0, max_value=220.0,
                                     value=float(profile["height_cm"]) if profile else 170.0, step=0.5)
        age = st.number_input("年齡", min_value=10, max_value=100,
                               value=int(profile["age"]) if profile else 22, step=1)
    with col2:
        sex_label = st.radio("性別", ["男性", "女性"],
                              index=0 if (not profile or profile["sex"] == "male") else 1,
                              horizontal=True)
        activity_level = st.selectbox(
            "活動量",
            list(calc.ACTIVITY_MULTIPLIERS.keys()),
            index=list(calc.ACTIVITY_MULTIPLIERS.keys()).index(profile["activity_level"])
            if profile and profile["activity_level"] in calc.ACTIVITY_MULTIPLIERS else 1,
        )
        goal = st.selectbox(
            "目標",
            list(calc.GOAL_CALORIE_ADJUSTMENT.keys()),
            index=list(calc.GOAL_CALORIE_ADJUSTMENT.keys()).index(profile["goal"])
            if profile and profile["goal"] in calc.GOAL_CALORIE_ADJUSTMENT else 0,
        )

    submitted = st.form_submit_button("計算並儲存目標", type="primary")

if submitted:
    sex = "male" if sex_label == "男性" else "female"
    targets = calc.calculate_targets(weight_kg, height_cm, age, sex, activity_level, goal)

    db.save_profile(
        height_cm=height_cm, age=age, sex=sex, activity_level=activity_level, goal=goal,
        target_calories=targets["target_calories"],
        target_protein_g=targets["target_protein_g"],
        target_carb_g=targets["target_carb_g"],
        target_fat_g=targets["target_fat_g"],
    )
    if not latest_weight or latest_weight["weight_kg"] != weight_kg:
        db.add_body_weight(weight_kg)

    st.success("已儲存!目標已更新。")
    st.rerun()

profile = db.get_profile()
if profile:
    st.divider()
    st.subheader("目前的每日目標")

    bmr = calc.calculate_bmr(default_weight, profile["height_cm"], profile["age"], profile["sex"])
    tdee = bmr * calc.ACTIVITY_MULTIPLIERS[profile["activity_level"]]

    c1, c2, c3 = st.columns(3)
    c1.metric("BMR(基礎代謝)", f"{round(bmr)} kcal")
    c2.metric("TDEE(每日總消耗)", f"{round(tdee)} kcal")
    c3.metric("目標熱量", f"{profile['target_calories']:.0f} kcal")

    c4, c5, c6 = st.columns(3)
    c4.metric("蛋白質目標", f"{profile['target_protein_g']:.0f} g")
    c5.metric("碳水目標", f"{profile['target_carb_g']:.0f} g")
    c6.metric("脂肪目標", f"{profile['target_fat_g']:.0f} g")
else:
    st.info("還沒有設定資料,填上面的表單後按下「計算並儲存目標」。")
