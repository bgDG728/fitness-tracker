from datetime import date

import pandas as pd
import streamlit as st

import coach
import db
import workout_parser

db.init_db()

st.set_page_config(page_title="訓練紀錄", page_icon="🏋️")
st.title("🏋️ 訓練紀錄")

selected_date = st.date_input("日期", value=date.today())
log_date = selected_date.isoformat()

existing_exercises = db.get_exercise_names()

with st.expander("⚡ 快速輸入(貼上你的訓練簡記語法)", expanded=False):
    st.caption(
        "動作名稱單獨一行;「固定/自由」+『重量*組數』空白分隔;"
        "組數用小數 .5 代表半組未完成(記 4 下),整數組數每組預設記 8 下;"
        "沒接續新動作名稱前,空行不會換動作。解析完會先給預覽,可直接改表格,"
        "按「確認匯入」才會真的寫進紀錄。"
    )
    quick_text = st.text_area(
        "貼上文字", height=150, key="quick_input_text",
        placeholder="上斜胸推\n固定32*2 36 41*1 45*1.5\n\n自由 10*2 8*2",
    )
    if st.button("解析", key="parse_quick_input"):
        parsed = workout_parser.parse_quick_input(quick_text)
        if not parsed:
            st.warning("沒解析出任何資料,檢查一下格式。")
            st.session_state.pop("quick_parsed_df", None)
        else:
            st.session_state["quick_parsed_df"] = pd.DataFrame([
                {
                    "動作": p.exercise, "器材": p.equipment, "重量(kg)": p.weight_kg,
                    "次數": p.reps, "備註": p.note,
                }
                for p in parsed
            ])

    if "quick_parsed_df" in st.session_state:
        anomaly_count = (st.session_state["quick_parsed_df"]["備註"].astype(str).str.len() > 0).sum()
        if anomaly_count:
            st.warning(f"有 {anomaly_count} 筆有備註(可能是半組估算或解析異常),匯入前確認一下重量/次數對不對。")
        st.write("解析預覽(可直接點兩下修改再匯入):")
        edited_df = st.data_editor(
            st.session_state["quick_parsed_df"], key="quick_parsed_editor",
            width="stretch", hide_index=True, num_rows="dynamic",
        )
        if st.button("✅ 確認匯入", type="primary", key="confirm_quick_import"):
            existing_today = db.get_workout_log(log_date)
            next_num = {}
            for s in existing_today:
                next_num[s["exercise"]] = max(next_num.get(s["exercise"], 0), s["set_number"])
            imported = 0
            for _, row in edited_df.iterrows():
                ex = str(row["動作"]).strip()
                if not ex:
                    continue
                next_num[ex] = next_num.get(ex, 0) + 1
                db.add_workout_set(
                    ex, next_num[ex], int(row["次數"]), float(row["重量(kg)"]),
                    note=str(row["備註"] or ""), equipment=str(row["器材"] or ""),
                    log_date=log_date,
                )
                imported += 1
            st.success(f"已匯入 {imported} 筆紀錄。")
            del st.session_state["quick_parsed_df"]
            st.rerun()

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

    current_goal = db.get_exercise_goal(exercise) or coach.DEFAULT_GOAL
    goal = st.selectbox(
        "🎯 這個動作的訓練目標", coach.GOALS,
        index=coach.GOALS.index(current_goal), key=f"goal_{exercise}",
    )
    if goal != current_goal:
        db.set_exercise_goal(exercise, goal)

    e1rm_info = coach.best_e1rm(history)
    if e1rm_info:
        target = coach.suggest_target_load(goal, e1rm_info["e1rm"])
        st.info(
            f"📐 **{goal}目標區間:{target['weight_low']}-{target['weight_high']}kg,"
            f"{target['reps_low']}-{target['reps_high']} 下,{target['rpe']}**\n\n"
            f"換算自你目前最佳預估1RM {e1rm_info['e1rm']}kg"
            f"(來自 {e1rm_info['log_date']}:{e1rm_info['weight_kg']}kg x {e1rm_info['reps']} 下)"
        )
        weekly_done = coach.weekly_set_count(history, reference_date=selected_date)
        gap_msg = coach.volume_gap_message(goal, weekly_done)
        if gap_msg:
            st.warning(f"📊 {gap_msg}")
        else:
            st.success(f"📊 這週(至所選日期)已做 {weekly_done} 組,在{goal}目標建議的週組數範圍內。")
    else:
        st.caption("還沒有 12 下以內的歷史組數可以估算目標區間(次數太高換算1RM誤差太大),先記錄幾組吧。")

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
            last_set["note"], equipment=last_set.get("equipment", ""), log_date=log_date,
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
    equipment = st.selectbox("器材(選填)", ["", "固定", "自由"])
    note = st.text_input("備註(選填)", placeholder="例如:RPE 8")

    submitted = st.form_submit_button("加入紀錄", type="primary")

if submitted:
    if not exercise:
        st.error("請填動作名稱。")
    else:
        db.add_workout_set(
            exercise, int(set_number), int(reps), weight_kg, note,
            equipment=equipment, log_date=log_date,
        )
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
st.subheader("各動作歷史最佳表現(PR,以預估1RM排序)")

all_sets = db.get_workout_log()
if all_sets:
    pr_rows = []
    for ex in sorted({s["exercise"] for s in all_sets}):
        best = coach.best_e1rm([s for s in all_sets if s["exercise"] == ex])
        if best:
            pr_rows.append({
                "動作": ex,
                "預估1RM(kg)": best["e1rm"],
                "來源": f"{best['weight_kg']}kg x {best['reps']}下",
                "日期": best["log_date"],
            })
    if pr_rows:
        pr_df = pd.DataFrame(pr_rows).sort_values("動作")
        st.dataframe(pr_df, width="stretch", hide_index=True)
        st.caption(
            "預估1RM(e1RM)用 Epley 公式換算,只採用 12 下以內的組數(換算誤差較可控)。"
            "反映的是「換算下來力量最強的那一組」,不是單純誰扛得最重——"
            "例如 90kg x8下 換算 e1RM 比 100kg x1下 還高,會被判定才是真正的 PR。"
            "不同器材(固定/自由)的紀錄視為同一個動作合併計算。"
        )
    else:
        st.info("還沒有 12 下以內的組數可以估算 1RM,先記錄幾組吧。")
else:
    st.info("還沒有任何訓練紀錄。")
