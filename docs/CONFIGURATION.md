# 配置文档

项目配置保存在 `config.json`，也支持环境变量覆盖。首次启动会自动生成空模板；开源用户也可以复制 `config.example.json` 为 `config.json` 后填写。环境变量清单见 `.env.example`。

## 邮箱配置

| 字段 | 说明 | 示例 |
| --- | --- | --- |
| `email_provider` | 邮箱服务商 | `qq` / `163` / `126` / `gmail` / `outlook` / `sina` / `sohu` / `icloud` / `custom` |
| `email` | 邮箱地址 | `name@qq.com` |
| `auth_code` | IMAP 授权码，不是登录密码 | `your-qq-auth-code` |
| `imap_host` | IMAP 服务器 | `imap.qq.com` |
| `imap_port` | IMAP 端口 | `993` |
| `mailbox_web_url` | 网页邮箱入口 | `https://mail.qq.com/` |
| `fetch_limit` | 首次同步或重置游标后的最大邮件数 | `100` |
| `auto_sync` | 是否自动同步 | `true` |
| `sync_interval_minutes` | 自动同步间隔 | `30` |

QQ 邮箱需要在网页端开启 IMAP/SMTP 后使用授权码。QQ 网页邮箱的单封邮件 `sid` 会随登录态失效，`mailbox_web_url` 应填写邮箱首页。

## 日志

| 字段 | 说明 |
| --- | --- |
| `log_level` | `INFO` 默认；`DEBUG` 仅测试时使用 |

## 缓存与保留

| 字段 | 默认 | 说明 |
| --- | --- | --- |
| `cache.model_cache_ttl_hours` | `24` | 模型列表缓存小时数 |
| `cache.log_retention_days` | `7` | 日志保留天数 |
| `cache.event_retention_days` | `30` | 事件保留天数 |
| `cache.cleanup_interval_hours` | `24` | 自动清理间隔 |

## 模型配置

| 字段 | 说明 |
| --- | --- |
| `model.enabled` | 是否启用模型提取事件 |
| `model.provider` | 模型厂家，预设见 `config_store.py` |
| `model.api_base` | OpenAI 兼容 API Base |
| `model.api_key` | API Key，接口响应中只返回掩码 |
| `model.model_name` | 具体模型名，可从 `/models` 接口拉取 |

预设厂家：OpenAI、DeepSeek、Moonshot Kimi、智谱 GLM、阿里云百炼 Qwen、SiliconFlow、Ollama、自定义 OpenAI 兼容服务。

## 数据文件

| 文件 | 说明 |
| --- | --- |
| `data/events.json` | 日历事件 |
| `data/sync_cursor.json` | 邮件同步游标 |
| `data/model_usage.json` | Token 用量与费用 |
| `logs/app.log` | 运行日志 |

## 环境变量

示例：

```bash
EMAIL_CALENDAR_EMAIL_PROVIDER=qq
EMAIL_CALENDAR_EMAIL=name@qq.com
EMAIL_CALENDAR_AUTH_CODE=your-auth-code
EMAIL_CALENDAR_LOG_LEVEL=INFO
EMAIL_CALENDAR_MODEL_ENABLED=false
```

完整变量名见 `.env.example`。
