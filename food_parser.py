"""
飲食「快速輸入」解析器 —— 把「克數+品名」的多行文字轉成結構化清單,交給呼叫端
去資料庫查最接近的品項。純文字規則解析,不接任何 AI/ML 模型。

語法:一行一項,克數跟品名前後順序、中間有沒有空格都可以,例如:
    300白飯
    100 菜
    白飯300
無法辨識出數字的行會被忽略(不強行猜測)。
"""

import re
from dataclasses import dataclass

_LEADING_NUM_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*(.+)$")
_TRAILING_NUM_RE = re.compile(r"^(.+?)\s*(\d+(?:\.\d+)?)$")


@dataclass
class ParsedFoodItem:
    query: str
    grams: float


def parse_quick_food_input(text: str) -> list[ParsedFoodItem]:
    items = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        m = _LEADING_NUM_RE.match(line)
        if m:
            grams, name = float(m.group(1)), m.group(2).strip()
        else:
            m = _TRAILING_NUM_RE.match(line)
            if not m:
                continue
            name, grams = m.group(1).strip(), float(m.group(2))

        if name:
            items.append(ParsedFoodItem(query=name, grams=grams))

    return items
