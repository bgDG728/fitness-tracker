from datetime import date

import pandas as pd
import streamlit as st

import coach
import db

db.init_db()

st.set_page_config(page_title="訓練紀錄", page_icon="🏋️")
st.title("🏋️ 訓練紀錄")

selected_date = st.date_input("日期", value=date.today())
log_date = selected_date.isoformat()

existing_exercises = db.get_exercise_names()

st.subheader("新增一組")

# 動作選擇放在表單外面,選了之後可以馬上顯示教練建議,不用等送出表單。
# 三種來源:動作目錄(分部位瀏覽,不用先知道動作名稱)、最近使用過、自訂輸入。
source_options = ["📚 動作目錄"]
if existing_exercises:
    source_options.append("🕒 最近使用過")
source_options.append("✏️ 自訂輸入")

source = st.radio("動作來源", source_options, horizontal=True, label_visibility="collapsed")

if source == "📚 動作目錄":
    body_part = st.selectbox("部位", list(coach.EXERCISE_CATALOG.keys()))
    exercise = st.selectbox("動作", coach.EXERCISE_CATALOG[body_part])
elif source == "🕒 最近使用過":
    exercise = st.selectbox("動作", existing_exercises)
else:
    exercise = st.text_input("動作名稱", placeholder="例如:懸垂划船")

# ---- 教練建議:重量/次數 + 姿勢要點 ----
default_reps, default_weight = 10, 20.0
if exercise:
    history = [s for s in db.get_workout_log() if s["exercise"] == exercise]
    suggestion = coach.suggest_next_set(exercise, history)
    if suggestion:
        st.info(
            f"💡 **建議這次:{suggestion['suggested_weight']}kg x {suggestion['suggested_reps']} 下**\n\n"
            f"{suggestion['reason']}"
        )
        default_weight = suggestion["suggested_weight"]
        # 建議次數是像 "9-10" 這樣的區間字串,表單預設值用區間下限。
        try:
            default_reps = int(str(suggestion["suggested_reps"]).split("-")[0])
        except (ValueError, IndexError):
            pass

    tips = coach.get_exercise_tips(exercise)
    images = coach.get_exercise_images(exercise)
    if tips or images:
        with st.expander(f"🧑‍🏫 {exercise} 姿勢要點與示範", expanded=False):
            if images:
                img_cols = st.columns(len(images))
                for col, img_url in zip(img_cols, images):
                    col.image(img_url, width="stretch")
                st.caption("圖片來源:free-exercise-db(公共領域,Unlicense)")
            if tips:
                for tip in tips:
                    st.markdown(f"- {tip}")

today_sets = [s for s in db.get_workout_log(log_date) if s["exercise"] == exercise]

if today_sets:
    last_set = today_sets[-1]
    if st.button(
        f"🔁 重複上一組({last_set['weight_kg']}kg x {last_set['reps']} 下)",
        width="stretch",
    ):
        db.add_workout_set(
            exercise, last_set["set_number"] + 1, last_set["reps"], last_set["weight_kg"],
            last_set["note"], log_date=log_date,
        )
        st.rerun()

with st.form("workout_form", clear_on_submit=True):
    next_set_number = len(today_sets) + 1

    col1, col2, col3 = st.columns(3)
    with col1:
        set_number = st.number_input("第幾組", min_value=1, value=next_set_number, step=1)
    with col2:
        reps = st.number_input("次數", min_value=1, value=default_reps, step=1)
    with col3:
        weight_kg = st.number_input("重量 (kg)", min_value=0.0, value=float(default_weight), step=2.5)
    note = st.text_input("備註(選填)", placeholder="例如:RPE 8")

    submitted = st.form_submit_button("加入紀錄", type="primary")

if submitted:
    if not exercise:
        st.error("請填動作名稱。")
    else:
        db.add_workout_set(exercise, int(set_number), int(reps), weight_kg, note, log_date=log_date)
        st.success(f"已加入:{exercise} 第 {set_number} 組")
        st.rerun()

st.divider()

st.subheader(f"{selected_date.isoformat()} 的訓練")

sets = db.get_workout_log(log_date)
if sets:
    df = pd.DataFrame(sets)
    total_volume = (df["reps"] * df["weight_kg"]).sum()
    st.metric("今日總訓練量(次數 × 重量加總)", f"{total_volume:.0f} kg")

    for ex in df["exercise"].unique():
        ex_df = df[df["exercise"] == ex][["set_number", "reps", "weight_kg", "note"]]
        ex_df.columns = ["組數", "次數", "重量(kg)", "備註"]
        st.markdown(f"**{ex}**")
        st.dataframe(ex_df, width="stretch", hide_index=True)

    del_options = {
        f"{s['exercise']} 第{s['set_number']}組 {s['weight_kg']}kg x {s['reps']}": s["id"]
        for s in sets
    }
    to_delete = st.selectbox("刪除某一組", ["-"] + list(del_options.keys()))
    if to_delete != "-" and st.button("確認刪除", type="secondary"):
        db.delete_workout_set(del_options[to_delete])
        st.rerun()
else:
    st.info("這天還沒有訓練紀錄。")

st.divider()
st.subheader("各動作歷史最大重量(PR)")

all_sets = db.get_workout_log()
if all_sets:
    all_df = pd.DataFrame(all_sets)
    pr = all_df.loc[all_df.groupby("exercise")["weight_kg"].idxmax()][
        ["exercise", "weight_kg", "reps", "log_date"]
    ].sort_values("exercise")
    pr.columns = ["動作", "最大重量(kg)", "當時次數", "日期"]
    st.dataframe(pr, width="stretch", hide_index=True)
else:
    st.info("還沒有任何訓練紀錄。")
