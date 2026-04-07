# Vmail 邮箱服务接入设计

**日期：** 2026-04-07

**目标：** 将 `https://vmail.dev/api/v1` 接入现有注册系统，使其同时支持：
- 在“邮箱服务管理”页新增可配置的 `Vmail` 服务
- 在注册页把已启用的 `Vmail` 服务作为可选邮箱来源
- 在后端按现有 `EmailServiceFactory` 机制创建、轮询、读取和删除 Vmail 邮箱
- 沿用现有敏感配置过滤、可用服务聚合和测试连接能力

## 设计结论

`Vmail` 适合按现有“自定义邮箱服务”模式接入，而不是复用 `YYDS Mail` 或 `DuckMail`。

原因：
- `Vmail` 鉴权同时支持 `X-API-Key` 与 `Authorization`，与现有服务实现风格一致
- 它的资源模型更接近“mailbox/messages”，和 `YYDS Mail`、`DuckMail` 的账户/消息轮询模式相近
- 当前项目已经把新增邮箱服务拆成四层：`EmailServiceType`、`src/services/<service>.py`、`src/web/routes/email.py`、`src/web/routes/registration.py` + 前端表单/下拉；沿用这条路径最稳

## 架构与边界

### 1. 后端服务层

新增 `src/services/vmail_mail.py`：
- 负责封装 Vmail REST API
- 实现 `create_email`
- 实现 `get_verification_code`
- 实现 `list_emails`
- 实现 `delete_email`
- 实现 `check_health`
- 可选实现 `get_email_messages` / `get_message_content`

实现策略：
- 使用现有 `HTTPClient + RequestConfig`
- 默认请求头使用 `X-API-Key`
- 对外暴露缓存后的 mailbox 信息，保证注册流程能复用 `service_id`
- 轮询消息列表时按 `receivedAt` 与 `otp_sent_at` 过滤旧邮件
- 提取验证码时先拼接 `from/subject/preview/text/html`

### 2. 服务注册层

需要把 `Vmail` 纳入统一工厂：
- `src/config/constants.py` 新增 `EmailServiceType.VMAIL`
- `src/services/__init__.py` 注册 `VmailService`

### 3. 管理接口层

在 `src/web/routes/email.py` 中接入：
- `/email-services/stats` 的 `vmail_count`
- `/email-services/types` 的 Vmail 类型描述和配置字段
- `filter_sensitive_config` 继续通过 `api_key` 屏蔽密钥

Vmail 配置字段：
- `base_url`，默认 `https://vmail.dev/api/v1`
- `api_key`，必填
- `default_domain`，可选
- `expires_in`，可选，默认 86400
- `timeout`，可选，默认 30
- `max_retries`，可选，默认 3
- `poll_interval`，可选，默认 3

### 4. 注册接入层

在 `src/web/routes/registration.py` 中接入两处：
- `_normalize_email_service_config` 中添加 `Vmail` 的兼容字段标准化
- 注册执行时允许从数据库选择已启用的 `vmail` 服务
- `/registration/available-services` 中返回 `vmail` 聚合项，供注册页下拉框展示

### 5. 前端层

邮箱服务管理页：
- `templates/email_services.html` 新增 Vmail 添加/编辑表单区块
- `static/js/email_services.js` 新增 subtype 映射、列表加载、表单序列化、回填逻辑

注册页：
- `static/js/app.js` 新增 `availableServices.vmail`
- 在邮箱来源下拉中增加 `Vmail` 分组
- 选择后展示已选择日志

## 错误处理

统一遵循现有邮箱服务实现风格：
- API 错误优先读取 `{ error: { message } }`
- 如果消息列表/详情返回异常，则更新服务状态为 degraded
- OTP 轮询超时返回 `None`，不抛出致命异常
- 健康检查失败返回 `False`

## 测试策略

先写失败测试，再实现：
- `tests/test_vmail_service.py`
  - 创建邮箱时带 API Key、默认域名、过期时间
  - 无缓存时按 mailbox/message 链路轮询验证码
  - 健康检查命中 mailbox 创建接口
- 路由/聚合测试
  - `tests/test_email_service_vmail_routes.py`
  - 覆盖服务类型暴露、工厂注册、注册页可用服务聚合

前端回归：
- 补一个轻量测试确认 `static/js/app.js` 已包含 `vmail`

## 风险与约束

- 当前工作区已有未提交改动，且多处命中邮箱服务相关文件；本次只在必要位置做最小改动，不回滚现有内容
- 不使用 git worktree，避免丢失你当前工作区中的相关未提交状态
- 不提交真实 API Key 到源码；仅按你提供的 Key 完成本地接入与验证
