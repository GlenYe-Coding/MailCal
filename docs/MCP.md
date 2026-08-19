# MCP 文档

MCP Server 名称：`mailcal-mcp`

## 启动方式

### stdio

```bash
python src/mcp_server.py
```

Codex 接入：

```bash
codex mcp add mailcal -- python D:/Project/MailCal/src/mcp_server.py
```

### streamable HTTP

```bash
python src/mcp_server.py --http --host 127.0.0.1 --port 5174
```

连接地址：`http://127.0.0.1:5174/mcp`

## 工具与参数约束

### `list_events`

列出日历事件，可按开始时间范围过滤。

| 参数 | 必填 | 类型 | 约束 |
| --- | --- | --- | --- |
| `start_date` | 否 | string | 可解析的 ISO 时间 |
| `end_date` | 否 | string | 可解析的 ISO 时间，必须晚于 `start_date` |

### `get_event`

查看单个事件。

| 参数 | 必填 | 类型 | 约束 |
| --- | --- | --- | --- |
| `event_id` | 是 | string | 非空事件 id |

### `sync_emails`

读取配置的邮箱并刷新日历事件。无参数。

### `list_models`

从配置的模型厂家获取可用模型列表。无参数。

### `get_status`

返回掩码配置、事件数量、数据文件和同步游标。无参数。

### `reset_sync_cursor`

重置邮箱同步游标。无参数。

### `get_usage`

返回按模型分组的 Token 用量和估算费用。无参数。

### `reset_usage`

清零模型 Token 统计。无参数。

### `add_event`

手动添加事件。

| 参数 | 必填 | 类型 | 默认 | 约束 |
| --- | --- | --- | --- | --- |
| `title` | 是 | string | - | 1-60 字符 |
| `start` | 是 | string | - | 可解析的 ISO 时间 |
| `end` | 否 | string | 空 | 必须晚于 `start`；缺省补 60 分钟 |
| `event_type` | 否 | string | `other` | `interview` / `assessment` / `event` / `meeting` / `deadline` / `other` |
| `description` | 否 | string | 空 | 最多 20000 字符 |
| `status` | 否 | string | `auto` | `auto` / `upcoming` / `ongoing` / `overdue` / `done` / `cancelled` |

### `update_event`

修改已有事件。

| 参数 | 必填 | 类型 | 约束 |
| --- | --- | --- | --- |
| `event_id` | 是 | string | 非空事件 id |
| `title` / `start` / `end` / `event_type` / `description` / `status` | 否 | string | 至少提供一个；约束与 `add_event` 一致 |

### `delete_event`

删除事件。

| 参数 | 必填 | 类型 | 约束 |
| --- | --- | --- | --- |
| `event_id` | 是 | string | 非空事件 id |

## 错误返回

校验失败返回：

```json
{
  "ok": false,
  "message": "title 必填; start 必填",
  "errors": ["title 必填", "start 必填"]
}
```

## 安全说明

- 默认只监听 `127.0.0.1`
- 工具不暴露邮箱授权码和模型 API Key
- 调用 `sync_emails` 会读取本地 `config.json` 中的邮箱配置
