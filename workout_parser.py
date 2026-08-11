"""
「快速輸入」規則式解析器 —— 把使用者自己習慣的簡記語法轉成結構化的訓練紀錄。
不接任何 AI/ML 模型,純文字規則解析,邏輯透明、免費、可離線,行為完全可預期。

語法規則(2026-08 跟使用者確認過):
- 一行只有文字、沒有數字 → 這行是「動作名稱」,之後沒標器材來源的行都算這個動作,
  直到下一個「動作名稱」出現為止(空行只是排版,不會重置目前動作)
- 一行開頭是「固定」或「自由」→ 器材標籤,套用到同一行後面的所有 weight*組數
- 一行也可以是「動作名稱 weight*組數...」寫在同一行,例如「背部划船 23*2 27*3」
- 「重量*N」:N 是「組數」不是次數。使用者的習慣是每組都抓 8 下當標準
  (DEFAULT_REPS_PER_SET),所以整數組數 N 會展開成 N 筆 reps=8 的紀錄
- 小數 .5 代表「多一組沒完全做完(半組)」,展開成一筆 reps=4(HALF_SET_REPS,
  抓 8 下的一半)的紀錄,並在 note 註記,方便使用者事後知道這筆是估算來的
- 沒有 "*" 的裸數字(例如「36」)→ 當作 1 組(reps=8)
- 無法辨識的片段(例如打字漏掉符號)不會被丟棄猜測,而是原樣當成一個「重量」值
  保留 anomaly 註記,交給呼叫端(UI 的解析預覽表)讓使用者自己修正,不做危險的自動猜測
"""

import re
from dataclasses import dataclass, field

DEFAULT_REPS_PER_SET = 8
HALF_SET_REPS = 4

_EQUIPMENT_KEYWORDS = ("固定", "自由")

# 使用者常打字漏掉空格,把動作名稱/器材標籤跟數字黏在一起,例如「固定321」
# (固定+32*1)、「背部高位23*1.5」(背部高位+23*1.5)。只在「中文字→數字」的
# 交界處補空格(不能用「任何非數字字元」,否則會誤切開 weight*組數 token 本身
# 的 * 或小數點,例如把「32*2」錯切成「32*」+「2」)。
_GLUE_FIX_RE = re.compile(r"([一-鿿])(?=\d)")

# 「重量」或「重量*組數」,允許 * × x X 當乘號。
_TOKEN_RE = re.compile(r"^(\d+(?:\.\d+)?)(?:[*×xX](\d+(?:\.\d+)?))?$")


@dataclass
class ParsedSet:
    exercise: str
    equipment: str
    weight_kg: float
    reps: int
    note: str = ""
    anomaly: bool = False


def parse_quick_input(text: str) -> list[ParsedSet]:
    text = _GLUE_FIX_RE.sub(r"\1 ", text)


    rows: list[ParsedSet] = []
    current_exercise = None

    for raw_line in text.splitlines():
        words = raw_line.split()
        if not words:
            continue

        name_words = []
        tokens = []  # (equipment, weight, sets)
        equipment = ""
        data_started = False

        for w in words:
            if w in _EQUIPMENT_KEYWORDS:
                equipment = w
                data_started = True
                continue
            m = _TOKEN_RE.match(w)
            if m:
                data_started = True
                weight = float(m.group(1))
                sets = float(m.group(2)) if m.group(2) else 1.0
                tokens.append((equipment, weight, sets))
                continue
            if not data_started:
                name_words.append(w)
            # 資料開始後出現的未知片段先忽略,不強行塞進任何欄位

        line_name = "".join(name_words) if name_words else None
        if line_name:
            current_exercise = line_name

        if not tokens:
            continue

        exercise = line_name or current_exercise
        if exercise is None:
            for eq, weight, sets in tokens:
                rows.append(ParsedSet(
                    exercise="(未指定動作)", equipment=eq, weight_kg=weight,
                    reps=DEFAULT_REPS_PER_SET, note="這行前面沒有動作名稱,請手動填動作",
                    anomaly=True,
                ))
            continue

        for eq, weight, sets in tokens:
            rows.extend(_expand_sets(exercise, eq, weight, sets))

    return rows


def _expand_sets(exercise: str, equipment: str, weight: float, sets: float) -> list[ParsedSet]:
    full_sets = int(sets + 1e-9)
    remainder = round(sets - full_sets, 2)

    out = [
        ParsedSet(exercise=exercise, equipment=equipment, weight_kg=weight, reps=DEFAULT_REPS_PER_SET)
        for _ in range(full_sets)
    ]

    if abs(remainder - 0.5) < 1e-6:
        out.append(ParsedSet(
            exercise=exercise, equipment=equipment, weight_kg=weight, reps=HALF_SET_REPS,
            note="半組(未完成,預設抓一半次數)",
        ))
    elif remainder > 1e-6:
        out.append(ParsedSet(
            exercise=exercise, equipment=equipment, weight_kg=weight, reps=DEFAULT_REPS_PER_SET,
            note=f"組數有非 .5 的小數({sets}),請確認次數是否正確",
            anomaly=True,
        ))

    if not out:
        out.append(ParsedSet(
            exercise=exercise, equipment=equipment, weight_kg=weight, reps=DEFAULT_REPS_PER_SET,
            note=f"組數({sets})無法正常展開,請確認",
            anomaly=True,
        ))

    return out
