# unit-bot 任务 Checklist

3–4 人小团队快速迭代版。只列**下一步要做的事**，做完打勾往下走。

状态：☐ 未开始 · 🟡 进行中 · ✅ 完成

---

## 🎯 当前目标（Sprint 1–2，约 6 周）

打通 **OCR 识别 → 标准件库 → Web 浏览** 闭环。

---

## A. 本地 OCR + ROI 框选

| # | 任务 | 负责 | 估时 | 状态 | 验收 |
|---|------|------|------|:---:|------|
| A1 | PaddleOCR / RapidOCR 在拆机图上选型对比 | 后端 | 1 天 | ☐ | 20 张图对比表 |
| A2 | `core/ocr_service.py`：支持全图 + ROI 裁剪两种调用 | 后端 | 3 天 | ☐ | CPU 单 ROI <200ms |
| A3 | `core/sku_matcher.py`：OCR 文本 → `components_lib.csv` Top-5 候选 | 后端 | 2 天 | ☐ | 已知型号 Top-1 命中 ≥85% |
| A4 | OCR API：`POST /api/ocr/recognize`（mode=auto\|roi）+ `/commit` | 后端 | 2 天 | ☐ | swagger + demo curl |

> 视觉模型（Qwen2-VL 等判断封装类型）暂缓到 Sprint 3 后，按需再做。

## B. Web UI（极简）

技术栈：**FastAPI + Next.js（或直接 Vite+React）+ Tailwind + shadcn/ui**；docker-compose 起服。

| # | 任务 | 负责 | 估时 | 状态 | 验收 |
|---|------|------|------|:---:|------|
| B1 | `web/` 骨架 + docker-compose | 全栈 | 1 天 | ☐ | 前后端联通 |
| B2 | 只读 API：`/api/components`、`/api/products`、`/api/teardowns` | 后端 | 2 天 | ☐ | 分页 + 关键字搜索 |
| B3 | 通用 `DataTable` + 三个列表页 | 前端 | 3 天 | ☐ | 能搜、能筛、能翻页 |
| B4 | `/ocr` 上传 + 框选 + 识别（用 [react-konva](https://konvajs.org/) 画框） | 前端 | 4 天 | ☐ | 框 5 个元器件能返回 SKU 候选 |
| B5 | `/ocr` 审核入库：下拉候选 SKU、编辑、提交 | 前端 | 2 天 | ☐ | 走通上传→识别→入库 |

> 仪表盘、价格曲线、BOM 上传页全部**不做**；有需要前先用 CLI 脚本输出 CSV。

## C. CLI 小工具

| # | 任务 | 负责 | 估时 | 状态 | 验收 |
|---|------|------|------|:---:|------|
| C1 | `scripts/compare_bom.py`：两款机型 8 桶并排 diff | 算法 | 2 天 | ☐ | 跑出任意两款机型报告 |
| C2 | `scripts/fetch_fcc.py` 集成 OCR（auto 模式批处理） | 后端 | 1 天 | ☐ | FCC ID 端到端跑通 |

---

**总计 ≈ 23 人日**（3 人 × 2 周冲刺 + 1 周缓冲）

---

## 🗓 下一批（Sprint 3+，按需要解锁）

做完上面再决定，以下仅作备忘：

- 动态价格爬虫（立创 / 1688 / Digi-Key）
- 降本建议引擎（溢价件识别 + 替代方案）
- OCR 视觉模型（判断封装 / 元器件类型）
- 市场调研爬虫 + 月度简报
- 数据血缘（来源链字段）
- BOM 分析 Web UI（目前 CLI 够用）
- 飞书双向同步

---

## 👥 分工建议（3–4 人）

| 人 | 主抓 |
|----|------|
| 后端 1 | A1–A4 + B2 + C2 |
| 前端 1 | B1 + B3–B5 |
| 全栈 / 算法 1 | C1 + OCR ↔ Web 联调 + 代码评审 |
| （可选）产品 / 采购 1 | 验收、样本标注、对齐需求 |

---

## 🔄 迭代节奏

- **每日站会 10 分钟**：昨天做了啥、今天做啥、卡在哪
- **每周一对齐 30 分钟**：更新本文件打勾、调整下周优先级
- commit message：`checklist: {ID} {动作}`，例如 `checklist: A2 本地推理服务完成`
