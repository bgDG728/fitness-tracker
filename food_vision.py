"""
拍照辨識食物——用開源 Chinese-CLIP(OFA-Sys,transformers 套件)做零樣本
(zero-shot)影像分類,完全免費、跑在本機 CPU,不需要任何 API 費用或金鑰。

做法:不訓練專屬模型,而是把 tfda_foods 資料庫裡所有食品名稱都算成一組文字
embedding(第一次使用時計算,存本機快取檔),使用者拍照後只需要算這一張照片的
影像 embedding,跟文字 embedding 做 cosine 相似度比對,回傳最相近的前幾名。
好處是清單完全跟著 tfda_foods 資料庫走,選到的食品保證查得到營養資料;
壞處是本質上仍是「以圖找最相近的文字」,不是精準分類,辨識結果只能當參考,
使用者需要自己從候選清單挑選正確的一筆(介面上會提供 Top 3 讓使用者確認)。

份量(克重)刻意不做影像估重:沒有參考物(硬幣、餐盤)的單張照片估重,
就算是最先進的研究模型誤差仍有 15-25%,免費方案更不可能準。與其做一個
不準的估重模型充數,這裡直接以「每 100g」的計算基礎為預設份量,交給使用者
在既有的「份量(g)」欄位手動調整成實際重量。
"""

from pathlib import Path

import numpy as np
import torch
from PIL import Image
from transformers import ChineseCLIPModel, ChineseCLIPProcessor

import db

MODEL_NAME = "OFA-Sys/chinese-clip-vit-base-patch16"
EMBEDDING_CACHE_PATH = Path(__file__).parent / "tfda_label_embeddings.npz"

_model = None
_processor = None


def _load_model():
    global _model, _processor
    if _model is None:
        _model = ChineseCLIPModel.from_pretrained(MODEL_NAME)
        _processor = ChineseCLIPProcessor.from_pretrained(MODEL_NAME)
        _model.eval()
    return _model, _processor


def _build_label_embeddings():
    """對 tfda_foods 全部食品名稱算一次文字 embedding,存檔快取供之後重複使用。"""
    model, processor = _load_model()
    foods = db.get_all_tfda_food_names()
    if not foods:
        raise RuntimeError("tfda_foods 是空的,請先執行 import_tfda.py 匯入食品資料庫。")

    sample_ids = [f["sample_id"] for f in foods]
    names = [f["name"] for f in foods]

    inputs = processor(text=names, padding=True, return_tensors="pt")
    with torch.no_grad():
        # transformers >=5 的 get_text_features 回傳的是帶 pooler_output 的物件,
        # 不是直接的 tensor(這點跟官方 docstring 範例的寫法不一致,實測發現的)。
        text_features = model.get_text_features(**inputs).pooler_output
    text_features = text_features / text_features.norm(p=2, dim=-1, keepdim=True)

    embeddings = text_features.numpy().astype("float32")
    np.savez(EMBEDDING_CACHE_PATH, sample_ids=np.array(sample_ids), embeddings=embeddings)
    return sample_ids, embeddings


def _load_label_embeddings():
    """
    讀快取的文字 embedding;如果快取檔不存在,或筆數跟目前 tfda_foods 對不上
    (代表資料庫重新匯入過),就重新計算一次。
    """
    current_count = db.get_tfda_food_count()
    if EMBEDDING_CACHE_PATH.exists():
        cached = np.load(EMBEDDING_CACHE_PATH, allow_pickle=False)
        if len(cached["sample_ids"]) == current_count:
            return list(cached["sample_ids"]), cached["embeddings"]
    return _build_label_embeddings()


def ensure_ready():
    """預先載入模型並算好文字 embedding 快取,給setup腳本主動呼叫用,避免使用者第一次拍照時要等。"""
    _load_label_embeddings()


def classify_image(image: Image.Image, top_k: int = 3) -> list[dict]:
    """
    回傳最相似的 top_k 個食品:[{sample_id, name, category, score}]
    score 是 -1~1 的 cosine 相似度,只能當「相對排序」參考、不是機率,
    辨識結果僅供輔助,使用者仍需自行從候選中確認是否正確。
    """
    model, processor = _load_model()
    sample_ids, label_embeddings = _load_label_embeddings()

    inputs = processor(images=image, return_tensors="pt")
    with torch.no_grad():
        image_features = model.get_image_features(**inputs).pooler_output
    image_features = image_features / image_features.norm(p=2, dim=-1, keepdim=True)

    similarities = (image_features.numpy() @ label_embeddings.T)[0]
    top_indices = np.argsort(similarities)[::-1][:top_k]

    id_to_food = {f["sample_id"]: f for f in db.get_all_tfda_food_names()}
    results = []
    for idx in top_indices:
        sid = str(sample_ids[idx])
        food = id_to_food.get(sid, {})
        results.append({
            "sample_id": sid,
            "name": food.get("name", sid),
            "category": food.get("category", ""),
            "score": float(similarities[idx]),
        })
    return results
