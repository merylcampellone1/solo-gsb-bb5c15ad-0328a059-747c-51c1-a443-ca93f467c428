"""自动方向检索：多方向检测、载荷校验筛选、同分固定取舍、冲突标记、
入选方向标注图逆变换、上传快照不变，以及 API / 报告归档联动。

运行：
    python -m pytest tests/test_orientation.py -q
或直接：
    python tests/test_orientation.py
"""
import io
import json
import os
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import dctwm as wm  # noqa: E402


def _test_image(size=512, seed=0):
    rng = np.random.RandomState(seed)
    y, x = np.mgrid[0:size, 0:size]
    base = (
        128
        + 40 * np.sin(2 * np.pi * x / 130)
        + 30 * np.cos(2 * np.pi * y / 95)
        + 20 * np.sin(2 * np.pi * (x + y) / 60)
    )
    noise = rng.normal(0, 12, (size, size))
    ych = np.clip(base + noise, 0, 255)
    cr = np.clip(128 + 30 * np.sin(2 * np.pi * x / 200)
                 + rng.normal(0, 8, (size, size)), 16, 240)
    cb = np.clip(128 + 30 * np.cos(2 * np.pi * y / 220)
                 + rng.normal(0, 8, (size, size)), 16, 240)
    ycc = np.stack([ych, cr, cb], axis=-1).astype(np.uint8)
    import cv2
    return cv2.cvtColor(ycc, cv2.COLOR_YCrCb2RGB)


def _png(arr: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG")
    return buf.getvalue()


# D4 群中各操作的逆：检索对上传图施加的变换 = 上传时所受方向失真的逆
INVERSE = {
    "original": "original",
    "rotate90": "rotate270",
    "rotate180": "rotate180",
    "rotate270": "rotate90",
    "mirror": "mirror",
    "mirror90": "mirror90",
    "mirror180": "mirror180",
    "mirror270": "mirror270",
}


# ---------------------------------------------------------------- 纯函数

def test_orientation_round_trip():
    rng = np.random.RandomState(1)
    rgb = rng.randint(0, 256, (300, 500, 3)).astype(np.uint8)
    for oid, _ in wm.ORIENTATIONS:
        warped = wm.apply_orientation(rgb, oid)
        back = wm.invert_orientation(warped, oid)
        assert back.shape == rgb.shape
        assert np.array_equal(back, rgb), oid
        # 旋转后尺寸交换
        k = wm._cw_k(oid)
        if k in (1, 3):
            assert warped.shape[:2] == (rgb.shape[1], rgb.shape[0])


def test_select_orientation_tie_break_and_conflict():
    labels = dict(wm.ORIENTATIONS)

    def c(oid, detected, conf=0.0, text=""):
        return wm.OrientationCandidate(
            oid, labels[oid], detected, confidence=conf, text=text)

    # 仅通过载荷校验的候选有效；同分按固定顺序（原向优先）
    best, valid, conflict, texts = wm.select_orientation([
        c("rotate180", True, 90, "A"), c("original", True, 90, "A"),
        c("mirror", True, 80, "A"), c("rotate90", False)])
    assert best.orientation == "original"
    assert len(valid) == 3 and not conflict

    # 原向无效时按顺序取 rotate90
    best, _, _, _ = wm.select_orientation([
        c("original", False), c("mirror270", True, 70, "A"),
        c("rotate90", True, 70, "A")])
    assert best.orientation == "rotate90"

    # 不同候选恢复不同文本 -> 冲突并去重列出
    best, valid, conflict, texts = wm.select_orientation([
        c("original", True, 95, "文本甲"), c("mirror", True, 95, "文本乙"),
        c("rotate180", True, 80, "文本甲")])
    assert conflict is True
    assert texts == ["文本甲", "文本乙"]
    assert best.text == "文本甲"  # 最佳候选不是唯一结论，但仍按规则选出

    # 全部无效
    best, valid, conflict, texts = wm.select_orientation(
        [c(oid, False) for oid, _ in wm.ORIENTATIONS])
    assert best is None and valid == [] and not conflict and texts == []


# ---------------------------------------------------------------- 算法链路

def test_multi_orientation_recovers_all_eight():
    img = _test_image(512, seed=0)
    emb = wm.embed_watermark(img, "方向恢复XYZ", strength="medium")
    for oid, _ in wm.ORIENTATIONS:
        target = emb.image if oid == "original" else wm.jpeg_compress(
            wm.apply_orientation(emb.image, oid), 80)
        res = wm.detect_watermark_multi_orientation(target)
        assert res.enabled
        assert res.detected, oid
        assert res.selected == INVERSE[oid], (oid, res.selected)
        assert res.text == "方向恢复XYZ"
        assert not res.conflict
        # 入选方向标注图已逆变换回上传图坐标，尺寸一致
        assert res.result.overlay is not None
        assert res.result.overlay.shape == target.shape


def test_non_square_mirror_rotation():
    base = _test_image(512, seed=2)[:384, :, :]      # 384x512
    emb = wm.embed_watermark(base, "镜像QR", strength="medium").image
    up = wm.jpeg_compress(wm.apply_orientation(emb, "mirror270"), 80)
    assert up.shape[:2] == (512, 384)
    res = wm.detect_watermark_multi_orientation(up)
    assert res.detected and res.text == "镜像QR"
    assert res.selected == "mirror270"
    assert res.result.overlay.shape == up.shape


def test_unwatermarked_image_all_directions_rejected():
    res = wm.detect_watermark_multi_orientation(_test_image(384, seed=9))
    assert not res.detected
    assert res.selected is None
    assert len(res.candidates) == 8
    assert all(not c.detected for c in res.candidates)
    assert res.result is None


def test_overlay_inverse_matches_upload_coordinates():
    """标注图逆变换后应与“上传图在原向上的标注”落在同一画面位置。"""
    img = _test_image(512, seed=4)
    emb = wm.embed_watermark(img, "逆变换校验", strength="medium")

    # 原向直接检测的标注
    direct = wm.detect_watermark(emb.image)
    assert direct.overlay is not None

    # 上传图先被顺时针 90° 旋转；自动检索选出 rotate270，标注逆变换回上传坐标
    rotated = wm.apply_orientation(emb.image, "rotate90")
    res = wm.detect_watermark_multi_orientation(rotated)
    assert res.selected == "rotate270"
    back = res.result.overlay
    assert back.shape == emb.image.shape
    # 逆变换后的标注图应与直接在原向得到的标注图近似一致（JPEG 缺席，
    # 这里不做压缩，块级网格逐像素对齐；只比较瓦片边框与着色覆盖区域）
    changed_direct = np.any(direct.overlay != emb.image, axis=2)
    changed_back = np.any(back != emb.image, axis=2)
    iou = ((changed_direct & changed_back).sum()
           / max((changed_direct | changed_back).sum(), 1))
    assert iou > 0.9, iou


# ---------------------------------------------------------------- API / 归档

def _fresh_client():
    tmp = tempfile.mkdtemp(prefix="wm-orient-")
    os.environ["WM_DATA_DIR"] = tmp
    os.environ["WM_MAX_JOBS"] = "200"
    for mod in ("app.main", "app.archive"):
        sys.modules.pop(mod, None)
    from fastapi.testclient import TestClient
    from app.main import app, DATA_DIR
    return TestClient(app), Path(DATA_DIR)


def test_api_orientation_search_and_report():
    client, data_dir = _fresh_client()
    img = _test_image(512, seed=0)
    r = client.post(
        "/api/embed",
        files={"image": ("img.png", _png(img), "image/png")},
        data={"text": "接口方向测试", "strength": "medium"})
    jid = r.json()["job_id"]
    wm_arr = np.array(Image.open(
        data_dir / jid / "watermarked.png").convert("RGB"))
    upload = wm.jpeg_compress(wm.apply_orientation(wm_arr, "rotate90"), 75)

    # 普通模式：不做方向枚举
    plain = client.post("/api/detect",
                        files={"image": ("up.png", _png(upload), "image/png")})
    assert plain.json()["orientation_search"] == {"enabled": False}

    # 自动模式
    r = client.post(
        "/api/detect",
        files={"image": ("up.png", _png(upload), "image/png")},
        data={"orientation_search": "true"})
    assert r.status_code == 200, r.text
    det = r.json()
    os_ = det["orientation_search"]
    assert os_["enabled"] is True
    assert os_["selected"] == "rotate270"
    assert det["detected"] and det["text"] == "接口方向测试"
    assert len(os_["candidates"]) == 8
    assert {c["orientation"] for c in os_["candidates"]} == {
        oid for oid, _ in wm.ORIENTATIONS}
    assert det["upload_only"] is True

    # 原始检测输入快照保持为上传图（未被逆变换/转正）
    src_p = next((data_dir / det["job_id"] / "detections").glob("*.source.png"))
    snap = np.array(Image.open(src_p).convert("RGB"))
    assert snap.shape == upload.shape
    assert np.array_equal(snap, upload)

    # 标注图在上传图坐标
    marked = np.array(Image.open(io.BytesIO(
        client.get(det["marked_det_url"]).content)))
    assert marked.shape == upload.shape

    # 检测记录含方向及候选摘要
    rec = json.loads((
        data_dir / det["job_id"] / "detections"
        / f"{det['detection_id']}.json").read_text("utf-8"))
    assert rec["orientation_search"]["selected"] == "rotate270"
    assert rec["orientation_search"]["candidates"][0]["orientation"] == "original"

    # 报告收录方向摘要且清单/哈希链校验通过
    rid = client.post(
        f"/api/jobs/{det['job_id']}/reports",
        json={"detection_ids": [det["detection_id"]]}).json()["report_id"]
    report = client.get(f"/api/reports/{rid}").json()
    d = report["detections"][0]
    assert d["orientation_search"]["enabled"] is True
    assert d["orientation_search"]["selected"] == "rotate270"
    assert len(d["orientation_search"]["candidates"]) == 8
    v = client.post(f"/api/reports/{rid}/verify").json()
    assert v["valid"] and v["archive"]["chain_ok"]


def test_api_job_detection_ignores_orientation_flag():
    """引用任务图片的普通检测始终走原流程，即使带了 orientation_search。"""
    client, _ = _fresh_client()
    r = client.post(
        "/api/embed",
        files={"image": ("img.png", _png(_test_image(512)), "image/png")},
        data={"text": "普通流程", "strength": "medium"})
    jid = r.json()["job_id"]
    client.post("/api/attack", json={"job_id": jid, "jpeg_quality": 95})
    det = client.post("/api/detect",
                      data={"job_id": jid, "orientation_search": "true"}).json()
    assert det["orientation_search"] == {"enabled": False}
    assert det["source"] == "target"
    assert det["detected"] and det["text"] == "普通流程"


def test_api_orientation_no_valid_candidate():
    client, data_dir = _fresh_client()
    det = client.post(
        "/api/detect",
        files={"image": ("p.png", _png(_test_image(384, seed=11)), "image/png")},
        data={"orientation_search": "true"}).json()
    os_ = det["orientation_search"]
    assert det["detected"] is False
    assert os_["enabled"] and os_["selected"] is None
    assert os_["conflict"] is False
    assert all(not c["detected"] for c in os_["candidates"])
    assert det["marked_det_url"] is None
    # 仍然生成可归档的检测记录（快照存在、无标注图）
    rid = client.post(
        f"/api/jobs/{det['job_id']}/reports",
        json={"detection_ids": [det["detection_id"]]}).json()["report_id"]
    assert client.post(f"/api/reports/{rid}/verify").json()["valid"] is True


if __name__ == "__main__":
    import inspect
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and inspect.isfunction(v)]
    for fn in fns:
        fn()
        print(f"[PASS] {fn.__name__}")
    print(f"\n{len(fns)} 个自动方向检索测试全部通过 ✔")
