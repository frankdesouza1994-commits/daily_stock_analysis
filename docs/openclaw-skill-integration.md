# openclaw Skill 集成指南

本文档说明如何通过 [openclaw](https://github.com/openclaw/openclaw) Skill 调用 daily_stock_analysis 的 REST API，实现在 openclaw 对话中触发股票分析的能力。

## 概述

- **集成方式**：openclaw Skill 通过 HTTP 调用 daily_stock_analysis（DSA）REST API
- **适用场景**：已部署 DSA API 服务，希望在 openclaw 对话中触发分析（如「帮我分析茅台」「analyze AAPL」）
- **同类消费方**：2026-08-11 上线的 [Grok Bot](https://x.ai/bot)（Skills / Routines / MCP / computer use）走同一套 REST 契约，不要另起平行 API。见 [Grok Bot 集成](grok-bot-integration.md)。

## 前置条件

1. **daily_stock_analysis 必须已运行**：执行 `python main.py --serve-only` 或通过 Docker 部署，使 API 长期可用
2. **openclaw 需具备 HTTP 调用能力**：如 `system.run` 执行 curl，或内置 HTTP 工具（如 api-tester 等）
3. **说明**：GitHub Actions 仅做定时任务，不长期暴露 API，需本地或 Docker 运行 DSA

## 核心 API 参考

| 接口 | 方法 | 用途 |
|------|------|------|
| `/api/v1/analysis/analyze` | POST | 触发分析（主入口） |
| `/api/v1/analysis/status/{task_id}` | GET | 异步任务状态 |
| `/api/v1/agent/chat` | POST | Agent 策略问股（需 `AGENT_MODE=true`） |
| `/api/health` | GET | 健康检查 |
| `/api/v1/dashboard` | GET / PUT / PATCH | 可编辑看板（见下文「可编辑看板」） |

### 触发分析请求体

```json
{
  "stock_code": "600519",
  "report_type": "detailed",
  "force_refresh": true,
  "async_mode": false
}
```

- `stock_code`：股票代码（必填）
- `report_type`：`simple` | `detailed` | `brief`
- `force_refresh`：布尔值，是否强制刷新（忽略缓存）
- `async_mode`：布尔值，`false` 时同步返回，`true` 时返回 202 + `task_id` 需轮询

**注意**：`force_refresh`、`async_mode` 为布尔类型，非字符串。

### 响应示例（同步模式）

```json
{
  "query_id": "abc123def456",
  "stock_code": "600519",
  "stock_name": "贵州茅台",
  "report": {
    "summary": {
      "analysis_summary": "...",
      "operation_advice": "持有",
      "action": "hold",
      "action_label": "持有",
      "trend_prediction": "看多",
      "sentiment_score": 75
    },
    "strategy": {
      "ideal_buy": "1850",
      "stop_loss": "1780",
      "take_profit": "1950"
    }
  },
  "created_at": "2026-03-13T10:00:00"
}
```

## 重要限制与说明

- **仅支持股票代码**：API 不接受中文名称（如「茅台」），需在 Skill 侧解析或提示用户提供代码（如 600519、AAPL）
- **同步模式耗时**：`async_mode: false` 时，单次分析约 2–5 分钟，需确保 openclaw 或 HTTP 客户端超时足够
- **异步模式**：`async_mode: true` 返回 202 + `task_id`，需轮询 `GET /api/v1/analysis/status/{task_id}` 直至 `status: completed`

## 股票代码格式

| 类型 | 格式 | 示例 |
|------|------|------|
| A股 | 6位数字 | `600519`、`000001`、`300750` |
| 北交所 | 8/4/92 开头 6 位，支持 `BJ` 前缀或 `.BJ` 后缀 | `920748`、`BJ920493`、`920493.BJ` |
| 港股 | hk + 5位数字 | `hk00700`、`hk09988` |
| 美股 | 1-5 字母（可选 .X 后缀） | `AAPL`、`TSLA`、`BRK.B` |
| 美股指数 | SPX/DJI/IXIC 等 | `SPX`、`DJI`、`NASDAQ`、`VIX` |

## 配置方式

在 `~/.openclaw/openclaw.json` 中配置：

```json
{
  "skills": {
    "entries": {
      "daily-stock-analysis": {
        "enabled": true,
        "env": {
          "DSA_BASE_URL": "http://localhost:8000"
        }
      }
    }
  }
}
```

- 本地部署：`http://localhost:8000` 或 `http://127.0.0.1:8000`
- 远程部署：替换为实际 URL
- **建议**：`DSA_BASE_URL` 勿以 `/` 结尾

## 错误响应格式

| 状态码 | error 字段 | 说明 |
|--------|-------------|------|
| 400 | `validation_error` | 参数错误（如缺少 stock_code） |
| 409 | `duplicate_task` | 该股票正在分析中，拒绝重复提交 |
| 500 | `internal_error` / `analysis_failed` | 分析过程发生错误 |

## 完整 SKILL.md 示例

将以下内容保存到 `~/.openclaw/skills/daily-stock-analysis/SKILL.md`：

```markdown
---
name: daily-stock-analysis
description: 调用 daily_stock_analysis API 进行股票智能分析。当用户询问「分析茅台」「analyze AAPL」「帮我看看 600519」等时使用。仅支持股票代码，不支持中文名称。
metadata:
  {"openclaw": {"requires": {"env": ["DSA_BASE_URL"]}, "primaryEnv": "DSA_BASE_URL"}}
---

## 触发条件

当用户请求分析某只股票时（如「分析茅台」「analyze AAPL」「帮我看看 600519」），使用本 Skill。

## 工作流程

1. **提取股票代码**：从用户消息中识别股票代码（如 600519、AAPL、hk00700）。若用户仅提供中文名称（如「茅台」），需提示用户提供股票代码，或使用常见映射（茅台→600519）。
2. **调用 API**：向 `{DSA_BASE_URL}/api/v1/analysis/analyze` 发送 POST 请求，请求体：
   ```json
   {"stock_code": "<提取的代码>", "report_type": "detailed", "force_refresh": true, "async_mode": false, "skills": ["bull_trend"]}
   ```
   > `skills` 为可选策略 ID 数组；历史字段 `strategies` 仍保留兼容，建议优先使用 `skills`。
3. **等待响应**：同步模式下分析约需 2–5 分钟，请确保 HTTP 客户端超时足够（建议 ≥300 秒）。
4. **解析结果**：从响应的 `report.summary` 中提取 `operation_advice`、`trend_prediction`、`analysis_summary`，从 `report.strategy` 中提取 `ideal_buy`、`stop_loss`、`take_profit`，以简洁格式呈现给用户。外部集成可继续只读取自由文本 `operation_advice`；若需要结构化展示，可优先读取可选的 `action` / `action_label`（八态：`buy|add|hold|reduce|sell|watch|avoid|alert`）。旧历史缺字段时可回退到 `operation_advice` 文本展示，但该回退不等价于稳定 API action；旧三态统计口径仍以 `decision_type` 为准。
5. **错误处理**：
   - 连接失败：提示检查 DSA 是否运行、DSA_BASE_URL 是否正确
   - 400：检查 stock_code 格式
   - 409：该股票正在分析中，可稍后重试或查询任务状态
   - 500：提示查看 DSA 日志排查

## 股票代码格式

- A股：6位数字（600519、000001）
- 北交所：8/4/92 开头 6 位，支持 BJ 前缀或 .BJ 后缀（920748、BJ920493、920493.BJ）
- 港股：hk + 5位数字（hk00700）
- 美股：1–5 字母（AAPL、TSLA、BRK.B）
- 美股指数：SPX、DJI、IXIC 等
```

## Agent 策略问股（可选）

若 daily_stock_analysis 已启用 `AGENT_MODE=true`，可调用 Agent 策略问股接口，支持多轮对话与多种策略（缠论、均线金叉等）：

```bash
# 将 {DSA_BASE_URL} 替换为实际配置的 API 地址（如 http://localhost:8000）
curl -X POST {DSA_BASE_URL}/api/v1/agent/chat \
  -H 'Content-Type: application/json' \
  -d '{"message": "用缠论分析 600519", "session_id": "optional-session-id"}'
```

响应包含 `content`（分析结论）和 `session_id`（用于多轮对话）。

## 可编辑看板（openclaw 读写）

DSA 提供一个持久化的自定义看板，Web 端位于侧边栏「看板」（`/dashboard`），openclaw 可通过 REST API 读取并编辑同一份内容。Web 页面每 15 秒自动同步一次，openclaw 写入后无需手动刷新。

### 接口

| 接口 | 方法 | 用途 |
|------|------|------|
| `/api/v1/dashboard` | GET | 读取看板（标题、描述、有序组件列表、`version`） |
| `/api/v1/dashboard` | PUT | 整体替换看板（`title`、`description`、`widgets`） |
| `/api/v1/dashboard` | PATCH | 仅修改 `title` / `description` |
| `/api/v1/dashboard/widgets` | POST | 添加组件，可选 `position` 指定插入位置（默认追加到末尾） |
| `/api/v1/dashboard/widgets/{id}` | PATCH | 修改组件；`data` 浅合并到原数据，`position` 可移动组件 |
| `/api/v1/dashboard/widgets/{id}` | DELETE | 删除组件（`expected_version`、`actor` 走 query 参数） |

所有写接口都接受可选字段：

- `actor`：写入方标识（建议 openclaw 固定传 `"openclaw"`），在 Web 端显示为「最近由 openclaw 更新」
- `expected_version`：期望的当前版本号；与服务端不一致时返回 `409 version_conflict`（`detail.current_version` 为最新版本），用于避免覆盖用户刚在 Web 上做的修改。不传则直接写入

每次写入成功都会返回完整看板，`version` 加 1。从未保存过的看板 `version` 为 `0`。

### 组件类型

| `type` | `data` 字段 | 说明 |
|--------|-------------|------|
| `markdown` | `content`（≤20000 字符） | Markdown 文本，支持 GFM 表格 |
| `metric` | `value`（字符串或数字）、`hint`、`tone`（`default` / `primary` / `success` / `warning` / `danger`） | 单个大号指标 |
| `stock_list` | `items: [{code, name?, note?}]`（≤100 项） | 股票列表 |

公共字段：`id`（不传则自动生成，≤64 字符，同一看板内唯一）、`title`（≤120 字符）、`width`（`sm`=1/4、`md`=1/2、`lg`=3/4、`full`=整行，默认 `md`）。一个看板最多 50 个组件。`data` 中出现未知字段会返回 `400 validation_error`。

### 示例

```bash
# 读取
curl {DSA_BASE_URL}/api/v1/dashboard

# 添加一个指标组件，并指定 id 方便后续更新
curl -X POST {DSA_BASE_URL}/api/v1/dashboard/widgets \
  -H 'Content-Type: application/json' \
  -d '{"id": "moutai-advice", "type": "metric", "title": "茅台建议", "width": "sm",
       "data": {"value": "持有", "hint": "情绪分 75", "tone": "primary"}, "actor": "openclaw"}'

# 只更新数值，保留 hint / tone
curl -X PATCH {DSA_BASE_URL}/api/v1/dashboard/widgets/moutai-advice \
  -H 'Content-Type: application/json' \
  -d '{"data": {"value": "加仓"}, "actor": "openclaw"}'

# 删除
curl -X DELETE '{DSA_BASE_URL}/api/v1/dashboard/widgets/moutai-advice?actor=openclaw'
```

### 看板 SKILL.md 示例

将以下内容保存到 `~/.openclaw/skills/dsa-dashboard/SKILL.md`（与上文分析 Skill 共用 `DSA_BASE_URL`）：

```markdown
---
name: dsa-dashboard
description: 读取和编辑 daily_stock_analysis 的自定义看板。当用户说「把分析结果放到看板」「更新看板」「看板上加一个…」「删掉看板上的…」时使用。
metadata:
  {"openclaw": {"requires": {"env": ["DSA_BASE_URL"]}, "primaryEnv": "DSA_BASE_URL"}}
---

## 工作流程

1. 先 `GET {DSA_BASE_URL}/api/v1/dashboard`，记下 `version` 和现有组件的 `id`、`type`、`title`。
2. 根据用户意图选择操作：
   - 新增：`POST /api/v1/dashboard/widgets`，组件类型只能是 `markdown`、`metric`、`stock_list`；给组件起一个稳定、可读的 `id`（如 `moutai-advice`）以便之后更新。
   - 修改：`PATCH /api/v1/dashboard/widgets/{id}`，`data` 只需传要改的字段。
   - 删除：`DELETE /api/v1/dashboard/widgets/{id}`。
   - 重新排版或批量重建：`PUT /api/v1/dashboard`，必须带上要保留的全部组件。
3. 每次写入都传 `"actor": "openclaw"` 和第 1 步拿到的 `"expected_version"`。
4. 若返回 409 `version_conflict`，说明用户刚在 Web 上改过，重新 GET 后在最新内容上重做修改。
5. 400 时按 `message` 修正字段（常见：未知 `type`、`tone` 取值错误、`stock_list.items` 缺少 `code`、`id` 重复）。
6. 完成后告诉用户改了哪些组件，并提示在 DSA Web 的「看板」页面查看。

## 组件 data 格式

- markdown: {"content": "..."}
- metric: {"value": "12.3%", "hint": "可选说明", "tone": "default|primary|success|warning|danger"}
- stock_list: {"items": [{"code": "600519", "name": "贵州茅台", "note": "可选备注"}]}
- width: sm | md | lg | full
```

## 故障排查

| 现象 | 可能原因 | 处理建议 |
|------|----------|----------|
| 连接失败 | DSA 未运行、端口错误、防火墙 | 确认 `python main.py --serve-only` 已启动，检查 `DSA_BASE_URL` |
| 400 错误 | stock_code 格式错误或缺失 | 检查代码格式（见上文表格），确保请求体包含 `stock_code` |
| 500 错误 | AI 配置、数据源、网络问题 | 查看 DSA 日志，确认 `LITELLM_MODEL` 与对应 Key（如 `GEMINI_API_KEY` / `XAI_API_KEY`）已配置 |
| Agent 400 | Agent 模式未启用 | 在 DSA 的 `.env` 中设置 `AGENT_MODE=true` |
| 分析超时 | 同步模式等待时间过长 | 增加 HTTP 客户端超时，或改用 `async_mode: true` 轮询状态 |

## 认证说明

默认情况下 DSA API 无需认证。若在 `.env` 中启用了 `ADMIN_AUTH_ENABLED=true`，则需在 Skill 调用时携带登录后获得的 Cookie，具体方式取决于 openclaw 的 HTTP 工具能力（当前 API 仅支持 Cookie 认证，不支持 Bearer Token）。例如使用 curl 时可先登录并保存 Cookie，再在后续请求（包括看板读写）中复用：

```bash
curl -c dsa.cookie -X POST {DSA_BASE_URL}/api/v1/auth/login \
  -H 'Content-Type: application/json' -d '{"password": "<管理员密码>"}'
curl -b dsa.cookie {DSA_BASE_URL}/api/v1/dashboard
```
