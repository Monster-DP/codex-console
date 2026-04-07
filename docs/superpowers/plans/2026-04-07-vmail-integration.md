# Vmail Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 Vmail 邮箱服务完整接入当前项目的邮箱管理页、注册页和后端邮箱服务工厂。

**Architecture:** 复用现有邮箱服务扩展模式，新增 `VmailService` 并在服务工厂、邮箱管理 API、注册可用服务聚合以及前端表单/下拉中接入。整体按 TDD 执行，先锁定后端行为测试，再补 UI 暴露与回归。

**Tech Stack:** Python, FastAPI, SQLAlchemy, curl_cffi HTTPClient, Vanilla JS, Pytest

---

### Task 1: 锁定 Vmail 后端行为测试

**Files:**
- Create: `tests/test_vmail_service.py`
- Create: `tests/test_email_service_vmail_routes.py`
- Modify: `tests/test_registration_ui_messages.py`

- [ ] **Step 1: 写 Vmail 服务失败测试**

验证：
- `create_email()` 会把 `domain` / `expiresIn` / `localPart` 发到 `/mailboxes`
- `get_verification_code()` 会先取消息列表，再取消息详情，并提取 6 位验证码
- `check_health()` 至少能通过创建邮箱链路证明鉴权有效

- [ ] **Step 2: 跑定向测试确认当前为红**

Run: `pytest tests/test_vmail_service.py tests/test_email_service_vmail_routes.py tests/test_registration_ui_messages.py -q`

Expected:
- 因为 `VmailService` 与路由尚未接入而失败

### Task 2: 实现 Vmail 后端服务与工厂注册

**Files:**
- Create: `src/services/vmail_mail.py`
- Modify: `src/config/constants.py`
- Modify: `src/services/__init__.py`

- [ ] **Step 1: 新增 `EmailServiceType.VMAIL`**
- [ ] **Step 2: 实现 `VmailService`**

包含：
- 统一请求头构建
- mailbox/message 缓存
- payload 解包与错误提取
- OTP 轮询与内容拼接

- [ ] **Step 3: 在工厂注册 `VmailService`**

- [ ] **Step 4: 跑后端服务测试确认变绿**

Run: `pytest tests/test_vmail_service.py -q`

### Task 3: 接入邮箱管理 API 与注册可用服务聚合

**Files:**
- Modify: `src/web/routes/email.py`
- Modify: `src/web/routes/registration.py`
- Modify: `tests/test_email_service_vmail_routes.py`

- [ ] **Step 1: 在邮箱管理 API 中增加 `vmail` 类型、统计和配置字段**
- [ ] **Step 2: 在注册执行分支中支持从数据库选取 `vmail` 服务**
- [ ] **Step 3: 在 `/registration/available-services` 中返回 `vmail` 聚合**
- [ ] **Step 4: 跑路由测试确认变绿**

Run: `pytest tests/test_email_service_vmail_routes.py -q`

### Task 4: 接入邮箱服务管理页与注册页展示

**Files:**
- Modify: `templates/email_services.html`
- Modify: `static/js/email_services.js`
- Modify: `static/js/app.js`
- Modify: `tests/test_registration_ui_messages.py`

- [ ] **Step 1: 在邮箱服务管理页新增 Vmail 添加/编辑字段**
- [ ] **Step 2: 在邮箱服务管理 JS 中新增 `vmail` subtype 的列表、文案、表单提交与编辑回填**
- [ ] **Step 3: 在注册页 JS 中新增 `availableServices.vmail` 与下拉选项**
- [ ] **Step 4: 跑前端轻量测试确认变绿**

Run: `pytest tests/test_registration_ui_messages.py tests/test_email_services_frontend_messages.py -q`

### Task 5: 整体验证

**Files:**
- Verify only

- [ ] **Step 1: 跑本次相关测试集合**

Run: `pytest tests/test_vmail_service.py tests/test_email_service_vmail_routes.py tests/test_email_services_frontend_messages.py tests/test_registration_ui_messages.py -q`

- [ ] **Step 2: 跑一轮更宽的邮箱服务回归**

Run: `pytest tests/test_yyds_mail_service.py tests/test_duck_mail_service.py tests/test_luckmail_service.py tests/test_registration_engine.py -q`

- [ ] **Step 3: 检查差异仅包含 Vmail 接入及当前工作区既有改动**

Run: `git status --short`
