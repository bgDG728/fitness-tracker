import altair as alt
import pandas as pd
import streamlit as st

import db

db.init_db()

st.set_page_config(page_title="進度圖表", page_icon="📈", layout="wide")
st.title("📈 進度圖表")

# 依照 dataviz 準則:單一數列用單一色相(藍,#2a78d6),
# 格線/軸線用低對比灰階,不做雙 y 軸。
SERIES_BLUE = "#2a78d6"
MUTED = "#898781"
GRIDLINE = "#e1e0d9"

BASE_AXIS = alt.Axis(gridColor=GRIDLINE, domainColor="#c3c2b7", tickColor="#c3c2b7", labelColor=MUTED, titleColor=MUTED)


def line_chart(df, x, y, y_title, tooltip_fmt=".1f"):
    # y 軸標題留空:中文直式標題會擠成一團,單位改用小標題文字+tooltip 傳達。
    line = (
        alt.Chart(df)
        .mark_line(color=SERIES_BLUE, strokeWidth=2)
        .encode(
            x=alt.X(x, title=None, axis=BASE_AXIS),
            y=alt.Y(y, title=None, axis=BASE_AXIS),
            tooltip=[alt.Tooltip(x, title="日期"), alt.Tooltip(y, title=y_title, format=tooltip_fmt)],
        )
    )
    points = (
        alt.Chart(df)
        .mark_circle(color=SERIES_BLUE, size=64)
        .encode(x=x, y=y, tooltip=[alt.Tooltip(x, title="日期"), alt.Tooltip(y, title=y_title, format=tooltip_fmt)])
    )
    return (line + points).properties(height=320).configure_view(strokeWidth=0)


# ---- 體重趨勢 ----
st.subheader("體重趨勢")
weight_log = db.get_body_weight_log()
if weight_log:
    df = pd.DataFrame(weight_log)
    df["log_date"] = pd.to_datetime(df["log_date"])
    st.altair_chart(line_chart(df, "log_date:T", "weight_kg:Q", "體重 (kg)"), use_container_width=True)
else:
    st.info("還沒有體重紀錄。到「個人設定」頁面更新體重會自動記錄一筆。")

st.divider()

# ---- 每日熱量攝取趨勢 ----
st.subheader("每日熱量攝取趨勢")
food_log = db.get_food_log()
profile = db.get_profile()
if food_log:
    df = pd.DataFrame(food_log)
    daily = df.groupby("log_date", as_index=False)["calories"].sum()
    daily["log_date"] = pd.to_datetime(daily["log_date"])

    line = (
        alt.Chart(daily)
        .mark_line(color=SERIES_BLUE, strokeWidth=2, point=alt.OverlayMarkDef(size=64, color=SERIES_BLUE))
        .encode(
            x=alt.X("log_date:T", title=None, axis=BASE_AXIS),
            y=alt.Y("calories:Q", title=None, axis=BASE_AXIS),
            tooltip=[alt.Tooltip("log_date:T", title="日期"), alt.Tooltip("calories:Q", title="攝取熱量", format=".0f")],
        )
    )
    chart = line
    if profile and profile.get("target_calories"):
        target_df = pd.DataFrame({"target": [profile["target_calories"]]})
        rule = (
            alt.Chart(target_df)
            .mark_rule(color=MUTED, strokeDash=[4, 4], strokeWidth=1.5)
            .encode(y="target:Q")
        )
        label = (
            alt.Chart(target_df)
            .mark_text(text="目標熱量", color=MUTED, align="left", dx=4, dy=-6, fontSize=11)
            .encode(y="target:Q", x=alt.value(0))
        )
        chart = rule + label + line

    st.altair_chart(chart.properties(height=320).configure_view(strokeWidth=0), use_container_width=True)
else:
    st.info("還沒有飲食紀錄。")

st.divider()

# ---- 訓練量趨勢 ----
st.subheader("訓練量趨勢(每日總訓練量 = 次數 × 重量加總)")
workout_log = db.get_workout_log()
if workout_log:
    df = pd.DataFrame(workout_log)
    df["volume"] = df["reps"] * df["weight_kg"]
    daily = df.groupby("log_date", as_index=False)["volume"].sum()
    daily["log_date"] = pd.to_datetime(daily["log_date"])

    bars = (
        alt.Chart(daily)
        .mark_bar(color=SERIES_BLUE, cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            x=alt.X("log_date:T", title="日期", axis=BASE_AXIS),
            y=alt.Y("volume:Q", title="訓練量 (kg)", axis=BASE_AXIS),
            tooltip=[alt.Tooltip("log_date:T", title="日期"), alt.Tooltip("volume:Q", title="訓練量", format=".0f")],
        )
        .properties(height=320)
        .configure_view(strokeWidth=0)
    )
    st.altair_chart(bars, use_container_width=True)

    st.subheader("單一動作歷史重量趨勢")
    exercises = sorted(df["exercise"].unique())
    picked = st.selectbox("選擇動作", exercises)
    ex_df = df[df["exercise"] == picked].groupby("log_date", as_index=False)["weight_kg"].max()
    ex_df["log_date"] = pd.to_datetime(ex_df["log_date"])
    st.altair_chart(line_chart(ex_df, "log_date:T", "weight_kg:Q", "當日最大重量 (kg)"), use_container_width=True)
else:
    st.info("還沒有訓練紀錄。")
