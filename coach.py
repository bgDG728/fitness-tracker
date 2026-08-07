"""
「教練建議」邏輯層 —— 讓系統不只是紀錄資料,而是主動給建議。

1. suggest_next_set()  用「雙重漸進」(double progression)邏輯,
   依上次訓練表現建議今天的重量/次數。這是重訓界很常見、有實證基礎的
   簡單漸進超負荷方法:先在同一個重量下把次數練到目標區間上限,
   達成後才加重量、次數退回下限,重新往上練。
2. EXERCISE_TIPS  常見動作的姿勢要點(文字提示,不涉及任何圖片/影片版權)。
3. diet_insight()  依今天營養素攝取 vs 目標的落差,給文字建議跟食物方向。
"""

# 次數目標區間:在這個區間內雙重漸進,超過上限才加重量
REP_RANGE_LOW = 6
REP_RANGE_HIGH = 10

# 標準漸進幅度:大肌群動作(下肢/複合動作)用較大幅度,小肌群/單關節動作用較小幅度
LARGE_MOVEMENT_STEP_KG = 2.5
SMALL_MOVEMENT_STEP_KG = 1.0

LARGE_MOVEMENT_KEYWORDS = ["深蹲", "硬舉", "臥推", "肩推", "划船", "squat", "deadlift", "bench", "press", "row"]


def _is_large_movement(exercise: str) -> bool:
    return any(kw.lower() in exercise.lower() for kw in LARGE_MOVEMENT_KEYWORDS)


def suggest_next_set(exercise: str, history_sets: list[dict]) -> dict | None:
    """
    history_sets: 該動作過去所有組數紀錄(dict list,含 log_date/reps/weight_kg),
    依時間排序皆可,函式內部會自己抓最近一次訓練日的表現。

    回傳 dict: {suggested_weight, suggested_reps, reason} 或 None(沒有歷史資料)。
    """
    if not history_sets:
        return None

    last_date = max(s["log_date"] for s in history_sets)
    last_sets = [s for s in history_sets if s["log_date"] == last_date]

    # 用上次訓練「最重那組」的表現當作漸進基準
    top_set = max(last_sets, key=lambda s: s["weight_kg"])
    weight = top_set["weight_kg"]
    reps = top_set["reps"]

    step = LARGE_MOVEMENT_STEP_KG if _is_large_movement(exercise) else SMALL_MOVEMENT_STEP_KG

    if reps >= REP_RANGE_HIGH:
        return {
            "suggested_weight": round(weight + step, 1),
            "suggested_reps": f"{REP_RANGE_LOW}-{REP_RANGE_LOW + 2}",
            "reason": (
                f"上次 {weight}kg 已經做到 {reps} 下,達到次數上限了,"
                f"這次加重到 {weight + step}kg,次數會掉回 {REP_RANGE_LOW} 下左右是正常的。"
            ),
        }
    elif reps < REP_RANGE_LOW:
        return {
            "suggested_weight": weight,
            "suggested_reps": f"{reps}-{reps + 2}",
            "reason": (
                f"上次 {weight}kg 只做到 {reps} 下,還沒到次數下限,"
                f"這次先維持同重量,專注把次數練起來,別急著加重。"
            ),
        }
    else:
        return {
            "suggested_weight": weight,
            "suggested_reps": f"{reps + 1}-{REP_RANGE_HIGH}",
            "reason": (
                f"上次 {weight}kg 做到 {reps} 下,在次數區間內,"
                f"這次同重量,目標多做 1 下,練到 {REP_RANGE_HIGH} 下之後再加重。"
            ),
        }


EXERCISE_TIPS: dict[str, list[str]] = {
    "深蹲": ["下蹲時膝蓋方向對齊腳尖,不要內夾", "全程核心收緊、背部打直,不要拱背或駝背", "重心放在腳掌中後段,別讓重心前移到腳尖", "下蹲深度至少大腿與地面平行"],
    "臥推": ["肩胛骨往後夾緊並穩定貼住椅面", "下放時手肘角度約 45-70 度,別讓手肘外展成 90 度", "槓鈴軌跡對齊胸口偏下方,不是脖子正上方", "全程保持核心穩定,腳掌踩穩地面"],
    "硬舉": ["起槓前背部打直、核心收緊,絕對不要圓背", "槓鈴貼近小腿脛骨往上拉,軌跡越直越好", "用髖關節發力(推髖)而不是純粹用下背出力", "鎖定時肩膀打開站直,不要過度後仰"],
    "肩推": ["核心收緊,避免過度後仰腰椎代償", "槓鈴/啞鈴軌跡盡量貼近臉部往上推", "手腕保持中立不要過度後折", "推到頂端時手臂打直但不要鎖死過度伸展"],
    "划船": ["身體前傾但背部打直,不要圓背", "用背部發力把手肘往後帶,不是純粹用手臂拉", "夾緊肩胛骨,頂點停頓一下感受背部收縮", "避免用整個上半身晃動借力"],
    "二頭彎舉": ["手肘固定在身體兩側,不要前後晃動借力", "全程控制速度,離心(放下)階段別讓重量直接掉下來", "手腕保持中立,不要過度彎曲", "避免用肩膀或身體擺盪借力"],
    "側平舉": ["手肘微彎,以肩膀為軸心帶動整條手臂", "抬到與肩同高即可,不要聳肩往上抬過頭", "控制速度,不要用甩的", "重量寧可輕一點也要維持正確動作軌跡"],
    "滑輪下拉": ["下拉時肩胛骨先下沉再出力,不要純粹用手臂拉", "身體微後傾但不要過度後仰借力", "拉到鎖骨附近即可,避免過度往下拉到腹部", "上拉(離心)階段全程控制,別放任滑輪快速回彈"],
    "臀推": ["肩膀上背靠穩在椅子/長凳邊緣", "頂端擠壓臀部 1-2 秒再放下", "避免用腰椎過度後仰代償,感覺應該在臀部而非下背", "下巴微收,避免頸部過度伸展"],
}


def get_exercise_tips(exercise: str) -> list[str] | None:
    for key, tips in EXERCISE_TIPS.items():
        if key in exercise or exercise in key:
            return tips
    return None


def diet_insight(total_cal, target_cal, total_protein, target_protein,
                  total_carb, target_carb, total_fat, target_fat) -> list[str]:
    """回傳今天的飲食建議文字列表(可能為空list代表目前狀況良好)。"""
    tips = []

    if target_cal:
        cal_ratio = total_cal / target_cal if target_cal else 0
        if cal_ratio < 0.5:
            tips.append("今天目前熱量攝取還不到目標的一半,如果已經接近晚上,記得補足避免熱量太低影響代謝與訓練表現。")
        elif cal_ratio > 1.15:
            tips.append("今天熱量已經超過目標 15% 以上,如果不是刻意增肌期的計畫性超補,晚一點的餐可以清淡一些。")

    if target_protein:
        protein_ratio = total_protein / target_protein if target_protein else 0
        if protein_ratio < 0.6:
            tips.append("蛋白質攝取偏低(不到目標 60%),可以考慮加雞蛋、雞胸肉、無糖豆漿、希臘優格或乳清蛋白補足。")

    if target_fat:
        fat_ratio = total_fat / target_fat if target_fat else 0
        if fat_ratio > 1.3:
            tips.append("脂肪攝取偏高(超過目標 30%),留意是不是有較多油炸或高油醬料的餐點。")

    if target_carb:
        carb_ratio = total_carb / target_carb if target_carb else 0
        if carb_ratio < 0.4 and total_cal > 0:
            tips.append("碳水攝取偏低,如果今天有安排訓練,適量碳水有助於維持訓練強度與恢復。")

    return tips
