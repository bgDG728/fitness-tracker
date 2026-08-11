"""
「教練建議」邏輯層 —— 讓系統不只是紀錄資料,而是主動給建議。

1. suggest_next_set()  用「雙重漸進」(double progression)邏輯,
   依上次訓練表現建議今天的重量/次數。這是重訓界很常見、有實證基礎的
   簡單漸進超負荷方法:先在同一個重量下把次數練到目標區間上限,
   達成後才加重量、次數退回下限,重新往上練。
2. EXERCISE_TIPS  常見動作的姿勢要點(文字提示,不涉及任何圖片/影片版權)。
3. diet_insight()  依今天營養素攝取 vs 目標的落差,給文字建議跟食物方向。
4. GOAL_ZONES / epley_1rm() / suggest_target_load() / volume_gap_message()
   依「訓練目標」(最大力量/肌肥大/肌耐力)給科學化的重量區間跟每週組數
   建議。數據來源見下方 GOAL_ZONES 註解,規則寫死在程式碼裡、不接任何
   AI/付費 API——這類目標對應的訓練參數已經有運動科學界的共識,寫成規則表
   就能涵蓋,邏輯透明、免費、你可以自己打開程式碼驗證合不合理。
"""

from datetime import date as _date, timedelta as _timedelta

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


# ---- 目標導向的科學化訓練建議 ----
#
# 三種常見訓練目標對應的強度(%1RM)、次數區間、每週組數區間、自覺強度,
# 數據參考 ACSM 2026 阻力訓練指引、NSCA 訓練建議,以及 Schoenfeld 等人
# 對訓練量-肌肥大劑量反應關係的統合分析:
# - 最大力量:80-100% 1RM,1-6下,每個動作每週至少 2-3 組起,RPE 8-10(0-2 RIR)
# - 肌肥大:60-80% 1RM,6-12下,每週 10-20 組是多數受訓者的有效區間
#   (5-9 組是有效下限,超過約 25 組沒有額外好處),RPE 7-9(1-3 RIR)
# - 肌耐力:40-60% 1RM,12下以上,RPE 6-8(2-4 RIR)
GOAL_ZONES: dict[str, dict] = {
    "最大力量": {"pct_1rm": (0.80, 1.00), "reps": (1, 6), "weekly_sets": (2, 5), "rpe": "RPE 8-10(0-2 RIR)"},
    "肌肥大": {"pct_1rm": (0.60, 0.80), "reps": (6, 12), "weekly_sets": (10, 20), "rpe": "RPE 7-9(1-3 RIR)"},
    "肌耐力": {"pct_1rm": (0.40, 0.60), "reps": (12, 20), "weekly_sets": (10, 20), "rpe": "RPE 6-8(2-4 RIR)"},
}
DEFAULT_GOAL = "肌肥大"
GOALS = list(GOAL_ZONES.keys())

# e1RM 公式在這個次數區間內誤差普遍在 5% 內,超過就不採用來估 1RM,
# 避免次數太高時嚴重高估(誤差可能到 15-20%)。
E1RM_MAX_REPS = 12


def epley_1rm(weight_kg: float, reps: int) -> float:
    """Epley 公式估算單次最大重量(estimated 1RM)。"""
    return round(weight_kg * (1 + reps / 30), 1)


def best_e1rm(history_sets: list[dict]) -> dict | None:
    """
    從某動作的歷史紀錄中,找出「換算成 e1RM 最高」的那一組,而不是單純
    「舉起最重的那次」——用 90kg 做 8 下换算下来的實際力量,可能比 100kg
    只做 1 下更強,單看重量會誤判 PR。
    """
    candidates = [s for s in history_sets if s["reps"] <= E1RM_MAX_REPS]
    if not candidates:
        return None
    best_set = max(candidates, key=lambda s: epley_1rm(s["weight_kg"], s["reps"]))
    return {
        "e1rm": epley_1rm(best_set["weight_kg"], best_set["reps"]),
        "weight_kg": best_set["weight_kg"],
        "reps": best_set["reps"],
        "log_date": best_set["log_date"],
    }


def suggest_target_load(goal: str, e1rm: float) -> dict:
    """依訓練目標 + 目前 e1RM,算出這次建議的重量區間跟次數區間。"""
    zone = GOAL_ZONES.get(goal, GOAL_ZONES[DEFAULT_GOAL])
    pct_low, pct_high = zone["pct_1rm"]
    reps_low, reps_high = zone["reps"]
    weekly_low, weekly_high = zone["weekly_sets"]
    return {
        "weight_low": round(e1rm * pct_low, 1),
        "weight_high": round(e1rm * pct_high, 1),
        "reps_low": reps_low,
        "reps_high": reps_high,
        "rpe": zone["rpe"],
        "weekly_sets_low": weekly_low,
        "weekly_sets_high": weekly_high,
    }


def weekly_set_count(history_sets: list[dict], reference_date: "_date | None" = None) -> int:
    """計算某動作在「過去 7 天(含今天)」總共做了幾組。"""
    reference_date = reference_date or _date.today()
    start = reference_date - _timedelta(days=6)
    return sum(
        1 for s in history_sets
        if start <= _date.fromisoformat(s["log_date"]) <= reference_date
    )


def volume_gap_message(goal: str, weekly_sets_done: int) -> str | None:
    """依目標的建議週組數區間,提示目前這週組數夠不夠、會不會過量。"""
    zone = GOAL_ZONES.get(goal, GOAL_ZONES[DEFAULT_GOAL])
    low, high = zone["weekly_sets"]
    if weekly_sets_done < low:
        return f"這週目前做了 {weekly_sets_done} 組,{goal}目標建議每週 {low}-{high} 組,還差 {low - weekly_sets_done} 組。"
    if weekly_sets_done > high:
        return f"這週已經做了 {weekly_sets_done} 組,超過{goal}目標建議的 {low}-{high} 組上限,注意恢復、別過度訓練。"
    return None


# 動作目錄:依部位分類,「訓練紀錄」頁用這個讓使用者用瀏覽的方式選動作,
# 不需要事先知道正確名稱才能新增。
EXERCISE_CATALOG: dict[str, list[str]] = {
    "胸": ["臥推", "上斜臥推", "啞鈴臥推", "啞鈴飛鳥", "伏地挺身", "撐體"],
    "背": ["硬舉", "划船", "滑輪下拉", "引體向上", "坐姿划船", "T槓划船"],
    "腿": ["深蹲", "腿推", "分腿蹲", "腿伸展", "腿彎舉", "羅馬尼亞硬舉", "站姿提踵"],
    "肩": ["肩推", "側平舉", "前平舉", "臉拉", "聳肩", "阿諾德肩推"],
    "手臂": ["二頭彎舉", "槌式彎舉", "三頭下壓", "骷髏碎", "牧師椅彎舉"],
    "核心": ["棒式", "捲腹", "俄羅斯轉體", "懸吊抬腿", "滑輪捲腹"],
    "臀": ["臀推", "臀橋"],
}

EXERCISE_TIPS: dict[str, list[str]] = {
    "深蹲": ["下蹲時膝蓋方向對齊腳尖,不要內夾", "全程核心收緊、背部打直,不要拱背或駝背", "重心放在腳掌中後段,別讓重心前移到腳尖", "下蹲深度至少大腿與地面平行"],
    "臥推": ["肩胛骨往後夾緊並穩定貼住椅面", "下放時手肘角度約 45-70 度,別讓手肘外展成 90 度", "槓鈴軌跡對齊胸口偏下方,不是脖子正上方", "全程保持核心穩定,腳掌踩穩地面"],
    "上斜臥推": ["椅背角度約 30-45 度,角度太高會變成偏肩推", "槓鈴軌跡對齊上胸,不是脖子", "肩胛骨一樣要夾緊穩定,不要聳肩", "手肘角度跟平板臥推一樣,別過度外展"],
    "啞鈴臥推": ["啞鈴軌跡比槓鈴更需要自己控制穩定,注意左右對稱", "下放深度可以比槓鈴略低,增加胸部伸展", "手腕保持中立,避免手腕過度後折", "頂端不要讓兩個啞鈴互敲,控制收力"],
    "啞鈴飛鳥": ["手肘全程微彎固定角度,不是打直的直臂動作", "感覺用胸部把手臂「抱」起來,不是用肩膀出力", "下放幅度以肩膀不感到夾擠疼痛為限", "頂端不需要完全鎖死,保持胸部張力"],
    "伏地挺身": ["身體全程呈一直線,不要塌腰或翹臀", "手掌略寬於肩,手肘下放角度約 45 度", "核心與臀部收緊,避免用腰部代償", "下放到胸口接近地面再推起,做完整範圍"],
    "撐體": ["身體微前傾更多練到胸,身體直立更多練到三頭", "下放到肩膀略低於手肘即可,別過度下沉造成肩關節壓力", "手肘不要完全鎖死打直,保持關節緩衝", "肩膀全程下沉,避免聳肩"],
    "硬舉": ["起槓前背部打直、核心收緊,絕對不要圓背", "槓鈴貼近小腿脛骨往上拉,軌跡越直越好", "用髖關節發力(推髖)而不是純粹用下背出力", "鎖定時肩膀打開站直,不要過度後仰"],
    "划船": ["身體前傾但背部打直,不要圓背", "用背部發力把手肘往後帶,不是純粹用手臂拉", "夾緊肩胛骨,頂點停頓一下感受背部收縮", "避免用整個上半身晃動借力"],
    "滑輪下拉": ["下拉時肩胛骨先下沉再出力,不要純粹用手臂拉", "身體微後傾但不要過度後仰借力", "拉到鎖骨附近即可,避免過度往下拉到腹部", "上拉(離心)階段全程控制,別放任滑輪快速回彈"],
    "引體向上": ["起始姿勢手臂完全伸直,做完整範圍", "用背部把身體「拉」上去,不是純粹用手臂彎舉", "下巴過槓或胸口接近槓即可,避免用甩動借力", "下放階段全程控制,不要直接放鬆掉下去"],
    "坐姿划船": ["軀幹打直,拉的時候不要過度後仰借力", "手肘貼近身體往後帶,夾緊肩胛骨", "起始位置手臂伸直,肩膀微微前引伸展背部", "全程保持核心穩定,腳踩穩踏板"],
    "T槓划船": ["背部打直、髖關節鉸鏈,不要圓背", "手肘往後上方帶,感受中背收縮", "避免用整個身體上下彈震借力", "頂點停頓一下再緩慢放下"],
    "腿推": ["下背全程貼緊椅背,不要離開椅墊", "膝蓋方向跟腳尖一致,避免內夾", "下放深度以膝蓋不超過安全角度、下背不離椅為限", "頂端膝蓋不要完全鎖死打直"],
    "分腿蹲": ["後腳只是輔助平衡,重量主要放在前腳", "下蹲時前膝方向對齊腳尖,不要往內夾", "軀幹維持直立或微前傾,不要過度前傾", "前腳下蹲深度到大腿與地面接近平行"],
    "腿伸展": ["動作頂點停頓一下,感受股四頭肌收縮", "放下時不要讓重量直接砸回去,全程控制", "座椅調整到膝蓋轉動軸心對齊機器軸心", "避免用甩動的方式借力"],
    "腿彎舉": ["全程控制速度,離心階段不要放任重量快速落下", "髖部全程貼緊椅墊,不要抬起來借力", "動作頂點停頓一下感受大腿後側收縮", "避免用臀部代償出力"],
    "羅馬尼亞硬舉": ["膝蓋微彎固定角度,主要靠髖關節鉸鏈往後推", "槓鈴/啞鈴貼近大腿前側下滑,軌跡越直越好", "背部全程打直,不要圓背", "下放到能感受到腿後側緊繃即可,不用勉強碰地"],
    "站姿提踵": ["動作頂點停頓一下,感受小腿完全收縮", "下放到腳跟低於腳掌、有伸展感的深度", "全程控制速度,不要用彈震的方式借力", "膝蓋保持自然微彎,不要鎖死"],
    "肩推": ["核心收緊,避免過度後仰腰椎代償", "槓鈴/啞鈴軌跡盡量貼近臉部往上推", "手腕保持中立不要過度後折", "推到頂端時手臂打直但不要鎖死過度伸展"],
    "側平舉": ["手肘微彎,以肩膀為軸心帶動整條手臂", "抬到與肩同高即可,不要聳肩往上抬過頭", "控制速度,不要用甩的", "重量寧可輕一點也要維持正確動作軌跡"],
    "前平舉": ["手肘微彎,避免完全打直造成肘關節壓力", "抬到與肩同高即可,不要過度往上抬", "全程控制速度,放下時不要直接鬆掉", "避免用身體晃動借力甩上去"],
    "臉拉": ["手肘抬高往後拉,拉繩末端朝向臉部兩側", "拉的時候想像把肩胛骨往後夾緊", "全程保持核心穩定,身體不要後仰借力", "這是矯正性動作,重量不用太重,重點在肩胛穩定"],
    "聳肩": ["直上直下聳肩,不要用肩膀畫圈轉動", "頂點停頓一下感受斜方肌收縮", "避免用手臂彎曲借力,手肘保持自然伸直", "重量不需要過重,避免聳肩時圓背"],
    "阿諾德肩推": ["起始位置掌心朝向自己,推起過程中旋轉到掌心朝前", "核心收緊避免腰椎過度後仰", "全程控制旋轉節奏,不要用甩的", "手肘不要鎖死,保持關節緩衝"],
    "二頭彎舉": ["手肘固定在身體兩側,不要前後晃動借力", "全程控制速度,離心(放下)階段別讓重量直接掉下來", "手腕保持中立,不要過度彎曲", "避免用肩膀或身體擺盪借力"],
    "槌式彎舉": ["握法為掌心相對(像握槌子),手肘固定不晃動", "全程控制速度,尤其離心放下階段", "避免聳肩或用身體擺盪借力", "這個握法比較練到前臂與肱橈肌"],
    "三頭下壓": ["手肘固定夾緊身體兩側,不要前後移動", "只有前臂在動,上臂保持不動", "頂端手臂伸直但不鎖死,感受三頭收縮", "避免用身體前傾借力下壓"],
    "骷髏碎": ["手肘固定朝上不要外八字展開", "下放時槓鈴往額頭/頭後方向下降,不是往胸口", "全程控制速度,避免手肘晃動", "重量不需要太重,這個動作對肘關節壓力較大"],
    "牧師椅彎舉": ["整個上臂緊貼椅墊,不要離開", "避免頂端完全放鬆甩動借力", "全程控制離心放下的速度", "手腕保持中立,不要過度彎曲"],
    "棒式": ["身體呈一直線,不要塌腰或翹臀", "核心收緊,想像肚臍往脊椎方向內收", "肩膀在手肘正上方,避免聳肩", "自然呼吸,不要憋氣"],
    "捲腹": ["用腹部力量把肩胛骨捲離地面,不是用脖子出力拉起上半身", "動作頂點停頓一下感受腹部收縮", "全程控制速度,放下時不要直接躺回去放鬆", "下巴與胸口保持一個拳頭的距離,避免低頭夾脖子"],
    "俄羅斯轉體": ["核心收緊、上半身微後傾但背部打直,不要圓背", "轉動來自軀幹旋轉,不是純粹手臂甩動", "腳可以懸空增加難度或著地降低難度,依能力調整", "動作放慢,避免用甩動的離心力代替肌肉控制"],
    "懸吊抬腿": ["全程避免身體前後擺盪借力,盡量固定懸吊", "用下腹部力量把腿抬起,不是純粹靠髖屈肌甩動", "放下時全程控制,不要直接讓腿自由落下", "抓握力不夠可以用助握帶,才不會抓握先力竭"],
    "滑輪捲腹": ["跪姿面向滑輪,用腹部捲曲的方式往下,不是用手臂下拉", "動作重點在脊椎屈曲,不是髖關節前彎", "頂點(捲曲底部)停頓一下感受收縮", "全程控制速度,避免借力甩動"],
    "臀推": ["肩膀上背靠穩在椅子/長凳邊緣", "頂端擠壓臀部 1-2 秒再放下", "避免用腰椎過度後仰代償,感覺應該在臀部而非下背", "下巴微收,避免頸部過度伸展"],
    "臀橋": ["肩膀與上背平貼地面,腳掌踩穩與髖同寬", "頂端擠壓臀部,避免用下背過度後仰代償", "全程核心收緊,避免腰部拱起", "下放時不要讓臀部完全砸回地面,保持張力"],
}


def get_exercise_tips(exercise: str) -> list[str] | None:
    if exercise in EXERCISE_TIPS:
        return EXERCISE_TIPS[exercise]
    for key, tips in EXERCISE_TIPS.items():
        if key in exercise or exercise in key:
            return tips
    return None


# 動作示範圖片:free-exercise-db(yuhonas/free-exercise-db),Unlicense(公共領域),
# 可自由使用不需授權/標註。只挑常見動作做中文對應,避免亂猜配錯圖。
EXERCISE_IMAGE_BASE = "https://raw.githubusercontent.com/yuhonas/free-exercise-db/main/exercises/"

EXERCISE_REFERENCE_IMAGES: dict[str, list[str]] = {
    "深蹲": ["Barbell_Squat/0.jpg", "Barbell_Squat/1.jpg"],
    "臥推": ["Barbell_Bench_Press_-_Medium_Grip/0.jpg", "Barbell_Bench_Press_-_Medium_Grip/1.jpg"],
    "上斜臥推": ["Barbell_Incline_Bench_Press_-_Medium_Grip/0.jpg", "Barbell_Incline_Bench_Press_-_Medium_Grip/1.jpg"],
    "啞鈴臥推": ["Dumbbell_Bench_Press/0.jpg", "Dumbbell_Bench_Press/1.jpg"],
    "啞鈴飛鳥": ["Dumbbell_Flyes/0.jpg", "Dumbbell_Flyes/1.jpg"],
    "伏地挺身": ["Pushups/0.jpg", "Pushups/1.jpg"],
    "撐體": ["Dips_-_Triceps_Version/0.jpg", "Dips_-_Triceps_Version/1.jpg"],
    "硬舉": ["Barbell_Deadlift/0.jpg", "Barbell_Deadlift/1.jpg"],
    "划船": ["Bent_Over_Barbell_Row/0.jpg", "Bent_Over_Barbell_Row/1.jpg"],
    "滑輪下拉": ["Wide-Grip_Lat_Pulldown/0.jpg", "Wide-Grip_Lat_Pulldown/1.jpg"],
    "引體向上": ["Pullups/0.jpg", "Pullups/1.jpg"],
    "坐姿划船": ["Seated_Cable_Rows/0.jpg", "Seated_Cable_Rows/1.jpg"],
    "T槓划船": ["Lying_T-Bar_Row/0.jpg", "Lying_T-Bar_Row/1.jpg"],
    "腿推": ["Leg_Press/0.jpg", "Leg_Press/1.jpg"],
    "分腿蹲": ["Split_Squats/0.jpg", "Split_Squats/1.jpg"],
    "腿伸展": ["Leg_Extensions/0.jpg", "Leg_Extensions/1.jpg"],
    "腿彎舉": ["Lying_Leg_Curls/0.jpg", "Lying_Leg_Curls/1.jpg"],
    "羅馬尼亞硬舉": ["Romanian_Deadlift/0.jpg", "Romanian_Deadlift/1.jpg"],
    "站姿提踵": ["Standing_Calf_Raises/0.jpg", "Standing_Calf_Raises/1.jpg"],
    "肩推": ["Standing_Military_Press/0.jpg", "Standing_Military_Press/1.jpg"],
    "側平舉": ["Side_Lateral_Raise/0.jpg", "Side_Lateral_Raise/1.jpg"],
    "前平舉": ["Front_Dumbbell_Raise/0.jpg", "Front_Dumbbell_Raise/1.jpg"],
    "臉拉": ["Face_Pull/0.jpg", "Face_Pull/1.jpg"],
    "聳肩": ["Barbell_Shrug/0.jpg", "Barbell_Shrug/1.jpg"],
    "阿諾德肩推": ["Kettlebell_Arnold_Press/0.jpg", "Kettlebell_Arnold_Press/1.jpg"],
    "二頭彎舉": ["Dumbbell_Bicep_Curl/0.jpg", "Dumbbell_Bicep_Curl/1.jpg"],
    "槌式彎舉": ["Hammer_Curls/0.jpg", "Hammer_Curls/1.jpg"],
    "三頭下壓": ["Triceps_Pushdown/0.jpg", "Triceps_Pushdown/1.jpg"],
    "骷髏碎": ["EZ-Bar_Skullcrusher/0.jpg", "EZ-Bar_Skullcrusher/1.jpg"],
    "牧師椅彎舉": ["Preacher_Curl/0.jpg", "Preacher_Curl/1.jpg"],
    "棒式": ["Plank/0.jpg", "Plank/1.jpg"],
    "捲腹": ["Crunches/0.jpg", "Crunches/1.jpg"],
    "俄羅斯轉體": ["Russian_Twist/0.jpg", "Russian_Twist/1.jpg"],
    "懸吊抬腿": ["Hanging_Leg_Raise/0.jpg", "Hanging_Leg_Raise/1.jpg"],
    "滑輪捲腹": ["Cable_Crunch/0.jpg", "Cable_Crunch/1.jpg"],
    "臀推": ["Barbell_Hip_Thrust/0.jpg", "Barbell_Hip_Thrust/1.jpg"],
    "臀橋": ["Barbell_Glute_Bridge/0.jpg", "Barbell_Glute_Bridge/1.jpg"],
}


def get_exercise_images(exercise: str) -> list[str] | None:
    if exercise in EXERCISE_REFERENCE_IMAGES:
        return [EXERCISE_IMAGE_BASE + p for p in EXERCISE_REFERENCE_IMAGES[exercise]]
    for key, paths in EXERCISE_REFERENCE_IMAGES.items():
        if key in exercise or exercise in key:
            return [EXERCISE_IMAGE_BASE + p for p in paths]
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
