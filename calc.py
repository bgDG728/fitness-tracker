"""
TDEE(每日總消耗熱量)與三大營養素目標計算。

BMR 用 Mifflin-St Jeor 公式(目前實證上最準的簡易公式之一):
  男性: 10 * 體重(kg) + 6.25 * 身高(cm) - 5 * 年齡 + 5
  女性: 10 * 體重(kg) + 6.25 * 身高(cm) - 5 * 年齡 - 161
"""

ACTIVITY_MULTIPLIERS = {
    "久坐(幾乎不運動)": 1.2,
    "輕度運動(每週 1-3 天)": 1.375,
    "中度運動(每週 3-5 天)": 1.55,
    "高度運動(每週 6-7 天)": 1.725,
    "非常高強度(勞力工作 + 高強度訓練)": 1.9,
}

GOAL_CALORIE_ADJUSTMENT = {
    "減脂": -500,
    "維持": 0,
    "增肌": 300,
}

# 每公斤體重的蛋白質建議攝取量(g/kg),減脂時拉高一點保留肌肉
GOAL_PROTEIN_PER_KG = {
    "減脂": 2.2,
    "維持": 1.8,
    "增肌": 2.0,
}

FAT_RATIO_OF_CALORIES = 0.25  # 脂肪佔總熱量比例
KCAL_PER_G_PROTEIN = 4
KCAL_PER_G_CARB = 4
KCAL_PER_G_FAT = 9


def calculate_bmr(weight_kg: float, height_cm: float, age: int, sex: str) -> float:
    base = 10 * weight_kg + 6.25 * height_cm - 5 * age
    return base + 5 if sex == "male" else base - 161


def calculate_targets(weight_kg: float, height_cm: float, age: int, sex: str,
                       activity_level: str, goal: str) -> dict:
    bmr = calculate_bmr(weight_kg, height_cm, age, sex)
    tdee = bmr * ACTIVITY_MULTIPLIERS[activity_level]
    target_calories = tdee + GOAL_CALORIE_ADJUSTMENT[goal]

    protein_g = GOAL_PROTEIN_PER_KG[goal] * weight_kg
    fat_g = (target_calories * FAT_RATIO_OF_CALORIES) / KCAL_PER_G_FAT
    remaining_calories = target_calories - protein_g * KCAL_PER_G_PROTEIN - fat_g * KCAL_PER_G_FAT
    carb_g = max(remaining_calories, 0) / KCAL_PER_G_CARB

    return {
        "bmr": round(bmr),
        "tdee": round(tdee),
        "target_calories": round(target_calories),
        "target_protein_g": round(protein_g),
        "target_carb_g": round(carb_g),
        "target_fat_g": round(fat_g),
    }
