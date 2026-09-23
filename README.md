# 抗裁切水印实验台 · Block-DCT Watermark Bench

一个用于研究/演示**鲁棒数字图像水印**的 Web 实验平台。上传图片与一段短文本水印，系统在
**分块 DCT（离散余弦变换）频域**中把水印与同步标记平铺嵌入；嵌入后的图片即使经过
**JPEG 重压缩**与**中心裁切**，检测端仍能自动定位同步网格、通过重复块多数表决恢复文本，
并给出置信度与**疑似失真区域标注图**。

- 后端：Python 3.11 · FastAPI · OpenCV(headless) · Pillow · NumPy
- 前端：原生 HTML / CSS / JavaScript（无构建、无框架）
- 部署：Dockerfile + docker-compose.yml 一键启动

---

## 一、快速启动

### 方式 A：docker compose（推荐）

```bash
docker compose up -d --build
```

启动后浏览器访问：

> **http://localhost:8000**

停止 / 清理：

```bash
docker compose down            # 停止
docker compose down -v         # 停止并删除任务数据卷
```

### 方式 B：本地 Python 运行

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
WM_DATA_DIR=./data uvicorn app.main:app --host 0.0.0.0 --port 8000
```

访问 **http://localhost:8000** 。

> OpenCV headless 运行时需要系统库 `libgl1`、`libglib2.0-0`（Dockerfile 已安装）。

---

## 二、使用流程

页面按 **① 嵌入 → ② 施加攻击 → ③ 检测 / 标注** 三步组织：

1. **嵌入水印**：选择本地图片（最短边 ≥ 128px，建议 ≥ 512px 的自然照片），
   输入短文本（≤ 45 字节，约 45 个 ASCII 字符或 15 个汉字），选择强度后点击「嵌入水印」。
   页面显示 PSNR、同步瓦片数、每比特票数等指标，并可**下载无损含水印 PNG**。
2. **施加攻击**：拖动滑块选择 JPEG 质量（20–100）与中心裁切保留比例（30%–100%，
   裁切边界吸附到 8px DCT 网格），可多次叠加。点击「检测受攻击图片」。
3. **检测 / 标注**：
   - 自动执行 **64 种块相移全相关搜索**定位同步网格（不依赖图片边角，只要画面里还存在
     完整瓦片即可），再对所有瓦片相同槽位的载荷块做**跨瓦片多数表决**；
   - 显示恢复文本、总体置信度、同步相关峰、同步块一致率与逐比特置信度；
   - 「失真标注图」用颜色标出健康/受损瓦片、判决错误块、可疑弱块，可**下载 PNG**。

此外，「独立检测」区支持直接上传任意图片（含水印图、JPEG 转发件、截图等）进行盲检测，
并提供两种模式（页面上直接切换）：

- **普通检测（默认）**：仅按上传图原向执行一次检测，速度快，适合确认本台嵌入的图片；
- **自动方向检索**：对 **8 个方向** —— 原向、顺时针 90° / 180° / 270°，以及各自的
  **水平镜像** —— 逐一运行同一套水印检测，**仅把通过魔数 + 字节校验和载荷校验的结果
  视作有效候选**；再按置信度选出最佳方向（**同分按原向 → 90° → 180° → 270° → 镜像系
  的固定顺序取舍**）。
  - 检测结果面板会列出全部 8 个候选方向的校验结果、置信度与恢复文本；
  - 若不同有效候选**恢复出不同文本**，会明确标记「**方向候选冲突**」并列出候选文本——
    此时最佳候选**不是唯一结论**，需要人工甄别，面板不会把它当作唯一答案；
  - 入选方向的**失真标注图会被逆变换回上传图坐标**（即标注与上传画面逐像素对齐），
    而检测输入快照始终保存**上传原图**，不会被转正或镜像；
  - 方向、入选结果、冲突标记与候选摘要写入检测记录，并随检测记录一起进入
    **规范化 JSON 报告与哈希链归档**；
  - 耗时约为普通检测的 **8 倍**（8 次检测纯内存运行，不产生额外临时文件）。

> 自动方向检索仅对「独立上传检测」开放；引用任务图片（嵌入 / 攻击流程）的检测始终
> 按原流程执行，不受模式开关影响。

### 图片隐私检查（EXIF，只读）

页面最下方的「**图片隐私检查（EXIF）**」区支持上传一张 **PNG / JPEG** 照片，解析其 EXIF 中的：

- **拍摄时间**：优先 `DateTimeOriginal`，回退 `DateTime` / `DateTimeDigitized`，
  同时给出原始字符串与 ISO 8601 归一化结果；
- **相机品牌（Make）/ 型号（Model）**；
- **GPS 经纬度**：把度分秒三元组按 `N/S`、`E/W` 方向标记还原为**带符号十进制度**
  （南纬、西经为负），并保留原始度分秒文本对照。

字段缺失时明确显示「**无**」；EXIF 损坏或无法解码时不报错，图片仍正常检查，
并以黄色警告条提示。检查全程在内存中完成：**不保存图片或元数据、不创建任务**，
结果仅随当前 HTTP 响应返回，不影响水印任务、攻击记录与报告归档。

### 检测报告可验证归档

检测结果面板内可**勾选一次或多次检测结果**生成规范化 JSON 检测报告（归档）：

- 报告包含：报告 ID / 生成时间 / 生成器版本、嵌入参数（文本、强度、PSNR、瓦片数、
  算法常量快照）、每次检测的恢复文本、置信度、完整指标与当时的攻击参数，以及
  **原图 / 含水印图 / 受攻击图（检测输入快照）/ 失真标注图**的引用（路径 + URL + SHA-256）。
- 服务端为报告及其引用文件计算 **SHA-256 清单**（`manifest.entries`），报告写入
  `reports/<report_id>/report.json`，并向数据目录下**仅追加**的 `archive.log.jsonl`
  追加一条哈希链记录（`previous_entry_sha256` 串接，单条记录自带摘要）。
- 点击「校验清单完整性」会重算全部摘要：全部一致时报告通过；否则返回
  **首个缺失文件或首个摘要不一致项**，并同时报告归档哈希链状态（断链 / 记录被删改）。
- 可一键**下载 JSON 报告**；报告引用文件可通过报告中的 URL 单独下载。
- 报告存放在 `WM_DATA_DIR` 内，随 compose 命名卷持久化，且**不受任务数量上限清理影响**。
- 归档检测输入快照按检测记录单独保存（`detections/det_*.source.png`），
  后续继续叠加攻击不会改变既有报告引用的图片内容。

报告 JSON（节选）：

```json
{
  "schema_version": "1.0",
  "report_id": "rep_8b24aed3390e",
  "job_id": "756b2203d38f",
  "generated_at_iso": "2026-09-23T05:07:46Z",
  "detections": [
    {
      "detection_id": "det_f11ab49c384d",
      "source": "target",
      "detected": true,
      "text": "机密-2026",
      "confidence": 100.0,
      "metrics": { "sync_score": 1.0, "sync_agreement": 1.0 },
      "orientation_search": { "enabled": false },
      "attack_history": [ { "type": "jpeg", "quality": 65 } ],
      "references": [
        { "role": "attacked", "path": ".../det_xxx.source.png",
          "url": "/api/jobs/.../detections/det_xxx/source",
          "sha256": "f1ac…", "bytes": 119576, "exists": true }
      ]
    }
  ],
  "manifest": {
    "hash_algorithm": "sha-256",
    "entries": [ { "path": "…/original.png", "sha256": "20c4…", "bytes": 203749 } ]
  },
  "archive": { "log_path": "archive.log.jsonl", "seq": 1, "append_only": true }
}
```

> 报告自身的摘要 = SHA-256（报告删除 `manifest` 键后的规范化 JSON：UTF-8、键排序、
> 无空白），因此不存在摘要依赖自身的循环；规范化规则记录在
> `manifest.canonical_form` 中。

### 标注图颜色含义

| 颜色 | 含义 |
| --- | --- |
| 绿色瓦片底纹 | 该瓦片同步标记一致性高（≥ 80%） |
| 黄色瓦片底纹 | 同步标记部分受损（40%–80%） |
| 红色瓦片底纹 | 同步标记大面积失败（< 40%） |
| 绿色小块 | 同步块 / 载荷块判决正确 |
| 红色小块 | 块判决与恢复码流不一致（疑似被压缩/裁切破坏） |
| 黄色小块 | 判决正确但系数差值过小（临界弱块，重点观察区） |
| 蓝色网格线 | 128px 瓦片（同步周期）边界 |

---

## 三、算法说明

### 1. 分块 DCT 频域嵌入

- 图像转 YCrCb，仅在**亮度 Y 通道**处理；按 **8×8** 分块并做正交 DCT-II（与 JPEG 一致）。
- 每个 8×8 块用两对中频系数做**差值调制（spread-spectrum / QIM 风格）**：

  ```
  bit = 1  →  C(3,2) − C(2,3) > +δ      （第二对：C(4,1) − C(1,4)）
  bit = 0  →  差值 < −δ
  ```

  中频系数对 JPEG 量化有天然鲁棒性；差值形式对图像符号变化不敏感。
- `δ` 按强度档位（low / medium / high）给出，并乘以**纹理自适应因子**
  （平坦区域减小、纹理区域增大），兼顾不可见性与鲁棒性；嵌入经 3 轮迭代补偿
  IDCT 舍入与 0–255 裁剪导致的差值回落。

### 2. 同步标记 + 载荷平铺

- 每 **16×16 个块 = 128×128 像素**为一个**瓦片**，全图周期平铺：
  - 瓦片四角 4×4 共 **64 个同步块**，携带一段 **31 bit PN m 序列**（5 级 LFSR，
    自相关旁瓣 ≤ 1），用于确定瓦片网格的块级相位；
  - 其余 **192 个载荷块**，每块 2 bit，共 384 bit；码流
    `魔数 0xAB | 长度 | UTF-8 文本 | 校验和` 在**每个瓦片内重复平铺**。
- 检测端枚举 64 种块相移做归一化相关，取相关峰；允许整体符号翻转。
  因此**中心裁切后无需知道裁掉了多少**，只要画面里残留 ≥ 1 个完整瓦片并满足最少
  同步样本数即可对齐（实验图在保留 30% 边长时仍可恢复）。

### 3. 多数表决与置信度

- 所有瓦片**相同槽位**的载荷块按符号/软差值累加投票（瓦片内码流重复也贡献票数），
  得到软判决比特流；再从最大可能长度向下扫描，魔数与字节校验和同时通过才采信，
  显著降低误报。
- 置信度综合两类指标：
  - **软差值裕量**：平均系数差值相对 JPEG 量化步长的大小；
  - **投票一致率**：跨块投票中多数派占比。
- 逐块比对期望符号：同步块看 PN，载荷块看恢复码流；判决翻转块标红、
  临界弱块（|软差值| < 阈值）标黄，按瓦片聚合健康度。

### 3.1 自动方向检索（独立上传检测，可选）

- 对上传图生成 **8 个方向视图**（D4 二面体群）：原向、顺时针 90° / 180° / 270°，
  以及「先水平镜像再顺时针旋转」的 4 个方向；每个视图独立运行上述完整检测，
  **不放宽任何门限**——同步相关峰门限、魔数 `0xAB`、长度与字节校验和全部照旧，
  因此多方向枚举不会提高无水印图的误报率。
- 只有 `detected=True`（载荷校验通过）的方向进入候选；按总体置信度取最大，
  同分按固定顺序（原向优先，镜像系最后）取舍。
- 不同有效候选恢复出不同文本时标记**冲突**并去重列出候选文本；最佳候选
  仅按规则排序产生，不被表述成唯一结论。
- 入选方向的失真标注图做对应**逆刚体变换**（旋转 / 镜像，无重采样、无插值）
  映射回上传图坐标；90°/270° 方向伴随宽高交换，逆变换后恢复上传图尺寸。
  检测输入快照永远是上传原图本身。

### 4. 实测鲁棒性（合成测试图，medium 档）

**A. 纹理丰富的自然纹理图**（不可见性 PSNR ≈ 33 dB）

| 场景 | 结果 |
| --- | --- |
| 无攻击 | 置信度 100%，零失真块 |
| JPEG Q90 / Q70 / Q50 / Q40 / Q30 | 文本 100% 恢复 |
| JPEG Q25 / Q20 | 可恢复，置信度约 88% / 47% |
| 中心裁切保留 90% / 75% / 50% / 30% | 文本 100% 恢复 |
| 裁切 75% + JPEG Q60、裁切 50% + JPEG Q50 | 文本 100% 恢复 |
| 无水印图 | 正确判为「未检测到」 |

**B. 极度平滑的低频图**（PSNR ≈ 35.5 dB；JPEG 对平坦区量化最狠，是最坏情形）

| 强度 \ JPEG | Q40 | Q35 | Q30 | Q25 |
| --- | --- | --- | --- | --- |
| low | △（低置信度） | ✘ | ✘ | ✘ |
| medium | ✔ | ✔ | ✔（18%） | ✘（同步仍成功，校验失败） |
| high | ✔ | ✔ | ✔ | ✔（94%） |

> 复现：`python3 tests/test_core.py`。

> 提示：水印鲁棒性与图片内容相关。纹理丰富的照片表现最好；大片纯色/极暗区域、
> 极端低质量（Q < 25）JPEG、缩放/旋转/非 8 像素对齐裁切会明显增加误码——
> 这正是标注图与置信度的意义所在。

---

## 四、HTTP API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/` | 前端页面 |
| GET | `/api/health` | 健康检查 |
| POST | `/api/embed` | multipart：`image`(图片)、`text`、`strength`(low/medium/high)，返回任务 ID 与嵌入指标 |
| POST | `/api/attack` | JSON：`{job_id, jpeg_quality?, crop_fraction?}`，生成受攻击待测图 |
| POST | `/api/detect` | multipart：上传 `image` **或**传 `job_id`；可选 `orientation_search=true`（仅对独立上传生效，按原向/90°/180°/270° 及各自水平镜像共 8 方向逐一检测，仅采信通过载荷校验的候选），返回文本、置信度、指标、检测记录 ID、标注图 URL 与方向候选摘要 |
| POST | `/api/privacy-check` | multipart：上传 PNG/JPEG `image`，**只读**解析 EXIF 拍摄时间、相机品牌/型号、GPS（带符号十进制度）；不落盘、不建任务，字段缺失为 `null`，EXIF 损坏返回 200 + `warnings` |
| GET | `/api/jobs/{id}/{kind}` | 下载 `original` / `watermarked` / `target` / `marked` PNG |
| GET | `/api/jobs/{id}/detections/{det_id}/{kind}` | 下载某次检测的 `source`（检测输入快照）/ `marked`（标注图）PNG |
| POST | `/api/jobs/{id}/reports` | JSON：`{"detection_ids": ["det_…", ...]}`（1–20 条），生成可验证报告并追加归档，返回 `report_id`、`download_url`、`verify_url` |
| GET | `/api/reports/{report_id}` | 读取报告 JSON（内联）；加 `?download=1` 以下载附件 |
| POST | `/api/reports/{report_id}/verify` | 重算 SHA-256 清单；全部一致返回 200，否则返回 409 与**首个** `missing` / `digest_mismatch` 项及归档哈希链状态 |

检测响应（节选）：

```json
{
  "detected": true,
  "text": "机密-2026",
  "metrics": {
    "confidence": 98.7,
    "sync_score": 0.998,
    "sync_agreement": 0.99,
    "tiles_y": 3, "tiles_x": 3,
    "phase": [8, 8],
    "votes_per_bit": 18,
    "marked_blocks": 12,
    "total_blocks": 2304,
    "marked_fraction": 0.0052,
    "bit_confidences": [1.0, 0.98]
  },
  "marked_url": "/api/jobs/.../marked"
}
```

当 `orientation_search=true` 时，响应（及检测记录、报告中的每次检测）额外包含
`orientation_search` 块；普通检测该块固定为 `{"enabled": false}`：

```json
{
  "orientation_search": {
    "enabled": true,
    "selected": "rotate270",
    "selected_label": "逆时针 90°（顺时针 270°）",
    "detected": true,
    "conflict": false,
    "conflict_texts": [],
    "candidates": [
      { "orientation": "original",  "label": "原向",
        "detected": false, "confidence": 0.0, "text": "",
        "sync_score": 0.18, "sync_agreement": 0.0,
        "reason": "未找到同步网格（相关峰值过低）…" },
      { "orientation": "rotate90",  "label": "顺时针 90°", "detected": false, "...": "..." },
      { "orientation": "rotate180", "label": "180°",       "detected": false, "...": "..." },
      { "orientation": "rotate270", "label": "逆时针 90°（顺时针 270°）",
        "detected": true, "confidence": 100.0, "text": "机密-2026",
        "sync_score": 1.0, "sync_agreement": 1.0 },
      { "orientation": "mirror", "detected": false, "...": "..." },
      { "orientation": "mirror90", "detected": false, "...": "..." },
      { "orientation": "mirror180", "detected": false, "...": "..." },
      { "orientation": "mirror270", "detected": false, "...": "..." }
    ]
  }
}
```

> - 候选方向固定顺序：`original` → `rotate90` → `rotate180` → `rotate270`
>   → `mirror` → `mirror90` → `mirror180` → `mirror270`；同置信度时顺序靠前者入选。
> - 全部候选都未通过载荷校验时 `detected=false`、`selected=null`。
> - 多个有效候选恢复出不同文本时 `conflict=true`，`conflict_texts` 去重列出
>   各候选文本；顶层 `text` 仍是最佳候选文本，但它不代表唯一结论。
> - 入选方向的失真标注图已**逆变换回上传图坐标**；检测输入快照保存的仍是
>   **未转正的上传原图**。

隐私检查响应（节选；缺失字段为 `null`，前端显示「无」）：

```json
{
  "filename": "photo.jpg",
  "format": "JPEG",
  "width": 4032, "height": 3024,
  "exif_present": true,
  "exif_ok": true,
  "date_time": "2026:09:23 12:34:56",
  "date_time_iso": "2026-09-23T12:34:56",
  "camera_make": "AcmeCam",
  "camera_model": "Model X-100",
  "gps": {
    "latitude": 31.2625,
    "latitude_dms": "31° 15′ 45″ N",
    "latitude_ref": "N",
    "longitude": 121.5,
    "longitude_dms": "121° 30′ 0″ E",
    "longitude_ref": "E"
  },
  "warnings": [],
  "stored": false
}
```

> 度分秒换算：`十进制度 = 度 + 分/60 + 秒/3600`，南纬（S）/ 西经（W）取负号。
> EXIF 损坏或无法解码时 HTTP 状态码仍为 **200**，各字段为 `null`，
> `exif_ok=false` 并在 `warnings` 中说明原因；只有图片本身无法解码或不是
> PNG/JPEG 才返回 **400**，文件超过 16MB 返回 **413**。

---

## 五、配置项（环境变量）

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `WM_DATA_DIR` | `/data/wmbench` | 任务文件目录（原图/含水印图/攻击图/标注图，PNG）与归档目录（`reports/`、`archive.log.jsonl`） |
| `WM_MAX_JOBS` | `200` | 最多保留任务数，超出自动清理最旧任务（**归档报告不参与清理**） |

上传限制：单文件 ≤ **16MB**，最大边长 **4096px**，最短边 ≥ **128px**。
compose 默认把数据目录持久化到命名卷 `wm-data`；归档报告与仅追加日志
（`$WM_DATA_DIR/reports/`、`$WM_DATA_DIR/archive.log.jsonl`）随之持久化，
升级镜像后仍可下载与校验，Docker Compose 启动方式不变。

> 自动方向检索为页面/接口上的**可选模式**，无需额外环境变量、不改变
> Docker Compose 一条命令启动方式（`docker compose up -d --build`，访问
> http://localhost:8000 ）；它在内存中把检测重复 8 次，不产生额外配置与文件，
> 方向候选摘要随检测记录与报告一起归档。

### 嵌入参数（在 `app/dctwm.py` 顶部调整）

| 参数 | 含义 |
| --- | --- |
| `STRENGTH_DELTA` | 三档基础嵌入差值 δ（按 JPEG Q50 量化步长标定） |
| `TILE=16` / `SYNC=4` | 瓦片 16 块、同步角 4 块（周期 128px） |
| `SYNC_SCORE_THRESHOLD` | 同步相关峰判决门限（默认 0.42） |
| `WEAK_MARGIN` | 可疑弱块的软差值阈值（默认 14） |
| `PAIR_A / PAIR_B` | 两个调制系数对的位置 |

---

## 六、目录结构

```
.
├── app/
│   ├── dctwm.py          # 核心算法：DCT 嵌入 / PN 同步 / 相移搜索 / 多数表决 / 失真标注
│   ├── exifcheck.py      # 图片隐私检查：只读解析 EXIF 拍摄时间 / 相机 / GPS（损坏不阻断、不落盘）
│   ├── archive.py        # 检测报告：规范化 JSON / SHA-256 清单 / 仅追加哈希链归档 / 校验
│   ├── main.py           # FastAPI：任务存储、嵌入/攻击/检测/隐私检查/报告接口、静态资源
│   └── static/
│       ├── index.html    # 单页界面（嵌入 / 攻击 / 检测 / 隐私检查 / 归档 五区）
│       ├── style.css
│       └── app.js
├── tests/
│   ├── test_core.py        # 核心算法数值验证（DCT/PN/鲁棒性全链路）
│   ├── test_orientation.py # 自动方向检索：8 方向恢复 / 校验筛选 / 同分取舍 / 冲突 / 标注逆变换 / API+归档
│   ├── test_privacy.py     # 隐私检查接口：EXIF 解析 / DMS 还原 / 缺失与损坏 / 不落盘不阻断
│   └── test_reports.py     # 报告归档接口与清单/哈希链校验（篡改、缺失、断链）
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── README.md
```

运行核心算法测试（本地安装依赖后）：

```bash
python3 tests/test_core.py
python3 -m pytest tests/test_reports.py tests/test_privacy.py tests/test_orientation.py -q
```

数据目录布局（`WM_DATA_DIR`）：

```
<job_id>/
├── meta.json                         # 嵌入参数（独立上传检测时为 upload_only 轻量元数据）
├── original.png / watermarked.png / target.png / marked.png
└── detections/
    ├── det_xxxxxxxxxxxx.json         # 检测记录（文本/置信度/指标/攻击参数快照）
    ├── det_xxxxxxxxxxxx.source.png   # 该次检测输入快照
    └── det_xxxxxxxxxxxx.png          # 该次检测失真标注图
reports/rep_xxxxxxxxxxxx/report.json  # 规范化报告（含 SHA-256 清单）
archive.log.jsonl                     # 仅追加归档记录（哈希链）
```

---

## 七、安全与说明

- 本项目定位于**教学/研究实验台**，无鉴权、任务存于本地卷，请勿直接暴露到公网。
- 上传图片仅用于处理，不会上传到任何第三方；任务按数量自动过期清理。
- **图片隐私检查为纯只读操作**：图片与 EXIF 元数据均不写盘、不入库，
  仅在请求处理期间驻留内存，结果只返回给当前请求，不创建任务、不写入攻击记录与归档。
  照片分享前建议先用该功能确认 GPS 等敏感元数据是否需要清除。
- 数字水印的鲁棒性是概率性的，标注图与置信度用于辅助判断，不构成版权存证保证。
