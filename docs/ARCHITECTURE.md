# MailCal 架构文档

## 1. 系统总览

MailCal 由 Web 服务、MCP 服务和共享业务核心组成。Web 服务提供 HTML 日历和 REST API，MCP 服务提供 Codex 等工具接入，两者复用同一套清洗、提取、校验和存储逻辑。

```mermaid
flowchart LR
  subgraph Client["客户端"]
    UI["HTML 日历 UI"]
    Codex["Codex / MCP 客户端"]
    Rest["外部 REST 客户端"]
  end

  subgraph Entry["入口层"]
    App["app.py<br/>127.0.0.1:5173"]
    Mcp["mcp_server.py<br/>127.0.0.1:5174 / stdio"]
  end

  subgraph Core["业务核心"]
    Config["config_store"]
    Sync["mail_sync"]
    Clean["text_cleaner"]
    Extract["event_extractor"]
    Agent["model_agent<br/>LangGraph"]
    Validate["event_validation<br/>event_normalizer"]
    Catalog["model_catalog"]
    Usage["usage"]
  end

  subgraph Storage["本地存储"]
    Events[("events.json")]
    Cursor[("sync_cursor.json")]
    ModelUsage[("model_usage.json")]
    ModelCache[("models_cache.json")]
    Logs[("logs/app.log")]
  end

  IMAP[("QQ IMAP :993")]
  Provider["OpenAI / DeepSeek / Kimi / Ollama ..."]

  UI --> App
  Codex --> Mcp
  Rest --> App

  App --> Config
  App --> Sync
  Mcp --> Sync
  Sync --> IMAP
  Sync --> Clean
  Sync --> Extract
  Sync --> Agent
  Agent --> Provider
  App --> Catalog
  Catalog --> Provider

  Extract --> Validate
  Agent --> Validate
  Validate --> Events
  Sync --> Cursor
  App --> Events
  App --> Usage
  Usage --> ModelUsage
  App --> ModelCache
  App --> Logs
```

## 2. 模块分层

| 层 | 模块 | 职责 |
| --- | --- | --- |
| 入口 | `app.py` | HTML 页面、REST API、自动同步循环、后台管理 |
| 入口 | `mcp_server.py` | MCP stdio / streamable HTTP 工具 |
| 配置 | `config_store.py` | 配置文件、环境变量覆盖、邮箱/模型预设 |
| 同步 | `mail_sync.py` | IMAP 拉取、UID 游标、事件合并与持久化 |
| 清洗 | `text_cleaner.py` | HTML 转纯文本、去脚本样式、链接保留 |
| 提取 | `event_extractor.py` | 规则提取、可行动性判断、标题和时间推断 |
| 模型 | `model_agent.py` | LangGraph 调用模型并校验输出 |
| 模型 | `model_catalog.py` | 从模型厂家拉取真实模型列表并缓存 |
| 校验 | `event_validation.py` | API/MCP 共用的事件参数约束 |
| 校验 | `event_normalizer.py` | 时间格式、时区、结束时间规范化 |
| 状态 | `event_status.py` | 根据时间计算事件当前状态 |
| 用量 | `usage.py` | Token 消耗和费用统计 |
| 基础设施 | `file_io.py` / `logger.py` / `sync_cursor.py` | 原子写入、日志、同步游标 |

## 3. 邮件同步流水线

```mermaid
flowchart TD
  Trigger["自动同步 / POST /api/sync / MCP sync_emails"]
  Cursor["读取 sync_cursor.json"]
  Search["IMAP UID 搜索 last_uid + 1:*"]
  Fetch["拉取邮件 BODY.PEEK"]
  Clean["HTML 转纯文本"]
  Action{"是否可行动?"}
  Skip["跳过并记录日志"]
  Rule["规则提取事件"]
  Model["模型 Agent 提取事件"]
  Normalize["事件规范化与参数校验"]
  Merge["合并已有事件并去重"]
  Retention["按保留策略过滤"]
  Save["原子写入 events.json"]
  CursorSave["保存新游标"]

  Trigger --> Cursor
  Cursor --> Search
  Search --> Fetch
  Fetch --> Clean
  Clean --> Action
  Action -- "否" --> Skip
  Action -- "是" --> Rule
  Rule --> Normalize
  Clean --> Model
  Model --> Normalize
  Normalize --> Merge
  Merge --> Retention
  Retention --> Save
  Save --> CursorSave
```

## 4. API / MCP 写入链路

REST API 和 MCP 的事件写入共用 `event_validation.py`，保证参数约束和错误格式一致。

```mermaid
flowchart LR
  Rest["REST POST/PUT/DELETE /api/events"]
  Mcp["MCP add_event / update_event / delete_event"]
  Validate["event_validation"]
  Normalize["event_normalizer"]
  Store[("events.json")]
  Response["decorate + 响应"]
  Error["400 / 结构化 errors"]

  Rest --> Validate
  Mcp --> Validate
  Validate -- "不合法" --> Error
  Validate -- "合法" --> Normalize
  Normalize --> Store
  Store --> Response
```

## 5. 事件状态机

事件保存 `status` 时通常为 `auto`，展示层通过 `event_status.py` 根据当前时间推导 `upcoming / ongoing / overdue`；`done` 和 `cancelled` 为手动状态。

```mermaid
stateDiagram-v2
  [*] --> auto
  auto --> upcoming : now < start
  auto --> ongoing : start <= now <= end
  auto --> overdue : now > end
  upcoming --> ongoing : 到达开始时间
  ongoing --> overdue : 超过结束时间
  upcoming --> done : 手动完成
  ongoing --> done : 手动完成
  overdue --> done : 手动完成
  upcoming --> cancelled : 手动取消
  ongoing --> cancelled : 手动取消
  overdue --> cancelled : 手动取消
  done --> auto : 重新打开
  cancelled --> auto : 重新打开
```

## 6. 数据文件

| 文件 | 读写方 | 说明 |
| --- | --- | --- |
| `data/events.json` | `mail_sync.py`、`app.py`、`mcp_server.py` | 日历事件 |
| `data/sync_cursor.json` | `sync_cursor.py` | 增量同步游标 |
| `data/model_usage.json` | `usage.py` | Token 用量与费用 |
| `data/models_cache.json` | `model_catalog.py` | 模型列表缓存 |
| `logs/app.log` | `logger.py` | 运行日志 |
| `config.json` | `config_store.py` | 邮箱、模型和缓存配置 |
