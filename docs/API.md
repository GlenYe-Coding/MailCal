# REST API 文档

服务默认监听 `127.0.0.1:5173`。除下载原始邮件和 ICS 外，JSON 接口统一返回 `application/json; charset=utf-8`。

## 通用响应

成功返回业务字段；失败返回：

```json
{
  "ok": false,
  "message": "错误说明",
  "errors": ["字段级错误，可选"]
}
```

## 事件对象

```json
{
  "id": "a1b2c3d4e5f6a7b8",
  "title": "平安银行测评",
  "start": "2026-08-25T23:00:00",
  "end": "2026-08-26T00:00:00",
  "all_day": false,
  "type": "assessment",
  "color": "#e11d48",
  "status": "auto",
  "source_subject": "【平安银行】招聘评估邀请函",
  "source_from": "hr@pingan.com.cn",
  "description": "清洗后的邮件摘要",
  "links": [
    {
      "url": "https://example.com/test",
      "label": "在线测评链接"
    }
  ]
}
```

字段约束：

| 字段 | 必填 | 类型 | 约束 |
| --- | --- | --- | --- |
| `title` | 添加时必填 | string | 1-60 字符 |
| `start` | 添加时必填 | string | 可解析的 ISO 时间，存储为 `YYYY-MM-DDTHH:MM:SS` |
| `end` | 否 | string | 可解析的 ISO 时间，必须晚于 `start`；缺省自动补 60 分钟 |
| `type` | 否 | enum | `interview` / `assessment` / `event` / `meeting` / `deadline` / `other` |
| `status` | 否 | enum | `auto` / `upcoming` / `ongoing` / `overdue` / `done` / `cancelled` |
| `description` | 否 | string | 最多 20000 字符 |
| `color` | 否 | string | CSS 颜色 |

## 接口列表

### `GET /api/health`

健康检查。返回 `{"ok": true, "service": "mailcal"}`。

### `GET /api/state`

返回：

```json
{
  "config": {},
  "events": [],
  "sync": {},
  "sync_progress": {},
  "sync_cursor": {},
  "data_path": "",
  "usage": {},
  "meta": {}
}
```

`config` 中密钥已掩码。

### `GET /api/events`

返回全部事件：`{"events": []}`。

### `GET /api/events/{id}`

按事件 id 查询。不存在返回 `404`。

### `POST /api/events`

添加事件。请求体：

```json
{
  "title": "产品评审",
  "start": "2026-08-20T10:00:00",
  "end": "2026-08-20T11:00:00",
  "type": "meeting",
  "status": "auto",
  "description": "评审需求文档"
}
```

`title` 和 `start` 必填。校验失败返回 `400`。

### `PUT /api/events` / `PATCH /api/events`

修改事件。请求体：

```json
{
  "id": "a1b2c3d4e5f6a7b8",
  "title": "新的标题",
  "status": "done"
}
```

`id` 必填，其余字段至少提供一个。只修改提供的字段，时间仍遵循 `end` 必须晚于 `start` 的约束。

### `DELETE /api/events`

删除事件。请求体：`{"id": "a1b2c3d4e5f6a7b8"}`。

### `POST /api/sync`

立即同步邮箱，返回同步结果和当前事件列表。

### `GET /api/models`

从当前配置的模型厂家获取可用模型。可选查询参数：`refresh=1` 强制刷新缓存。

### `POST /api/models`

临时用指定模型配置获取模型列表：

```json
{
  "model": {
    "provider": "deepseek",
    "api_base": "https://api.deepseek.com/v1",
    "api_key": "sk-..."
  }
}
```

### `POST /api/config`

保存配置。省略 `auth_code` / `model.api_key` 时保留已保存值。保存前会校验邮箱、授权码、IMAP 端口、拉取数量等字段。

### `GET /api/usage`

返回按模型分组的 Token 用量和估算费用。

### `DELETE /api/usage`

清零 Token 统计。

### `DELETE /api/sync-cursor`

重置同步游标，下次同步会重新处理最近邮件。

### `GET /api/admin/stats`

返回邮件统计、事件数量、游标、用量和缓存配置。

### `GET /api/admin/logs`

查询参数：

| 参数 | 类型 | 默认 | 约束 |
| --- | --- | --- | --- |
| `lines` | integer | `200` | 最近日志行数 |
| `level` | string | 空 | `DEBUG` / `INFO` / `WARNING` / `ERROR` |

### `POST /api/admin/clear`

请求体：

```json
{"target": "expired"}
```

`target` 允许值：`models`、`logs`、`usage`、`cursor`、`events`、`expired`、`all`。

### `GET /api/emails/{uid}/raw`

通过 IMAP 按 UID 下载原始邮件，返回 `message/rfc822`，文件名为 `{uid}.eml`。

### `GET /api/export.ics`

导出全部日历事件的 ICS 文件。

### `GET /api/openapi.json`

返回 OpenAPI 3.0 摘要。

## 错误码

| HTTP | 场景 |
| --- | --- |
| `400` | 参数缺失、格式错误、校验失败 |
| `404` | 事件不存在、接口不存在、静态文件不存在 |
| `500` | 同步或服务内部异常 |
