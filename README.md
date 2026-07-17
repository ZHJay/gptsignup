# ChatGPT 批量注册工具

基于 `grokzhuce` 架构：自动注册 ChatGPT / OpenAI 账号，并在**同一 HTTP session** 内打开：

```text
https://chatgpt.com/api/auth/session
```

提取 `accessToken`（相对 Grok 的 `sso`）。

## 邮箱后端

**Outlook Email Plus** 邮箱池（`/api/external/*`），不再使用 Cloudflare Temp Mail。

| 步骤 | 接口 |
|------|------|
| 领取邮箱 | `POST /api/external/pool/claim-random` |
| 取验证码 | `GET /api/external/verification-code` |
| 成功回写 | `POST /api/external/pool/claim-complete` |
| 失败释放 | `POST /api/external/pool/claim-release` |

前置条件：在 Outlook Email Plus 后台导入可用的 **Outlook/IMAP 账号** 到邮箱池（`provider=outlook` 或 `imap`），并开启对外 API + 邮箱池。

## 快速开始（本地）

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # 填 OEP_BASE_URL / OEP_API_KEY
python chatgpt.py                  # 交互
python chatgpt.py --yes -w 3 -n 5  # 非交互
```

## Docker（小站推荐）

```bash
cp .env.example .env && chmod 600 .env
# OEP_BASE_URL=http://host.docker.internal:5001
# OEP_API_KEY=...
mkdir -p keys && chmod 700 keys

docker compose build
docker compose --profile tools run --rm gptsignup --yes -w 3 -n 1
```

环境变量：

| 变量 | 说明 |
|------|------|
| `OEP_BASE_URL` | Outlook Email Plus 根地址 |
| `OEP_API_KEY` | 对外 API Key（`X-API-Key`） |
| `OEP_PROVIDER` | 池筛选，默认 `outlook`；勿用 `cloudflare_temp_mail` |
| `OEP_PROJECT_KEY` | 项目隔离 key，默认 `gptsignup` |
| `OEP_CALLER_ID` | 调用方标识 |
| `PROXY` | 访问 OpenAI 的代理 |
| `GPT_WORKERS` / `GPT_TOTAL` | 默认并发 / 数量 |

输出挂载：`./keys` → 容器 `/app/keys`。

## 小站部署与 push 自动更新

路径约定：`ubuntu@小站:~/gptsignup`

### 1. 服务器 bootstrap（一次性）

```bash
cd ~
mv gptsignup gptsignup.bak 2>/dev/null || true
git clone https://github.com/ZHJay/gptsignup.git gptsignup
cp gptsignup.bak/.env gptsignup/.env
chmod 600 gptsignup/.env
mkdir -p gptsignup/keys && chmod 700 gptsignup/keys
cd gptsignup
bash deploy/deploy.sh
```

### 2. GitHub Secrets

| Secret | 示例 |
|--------|------|
| `SMALL_HOST` | `141.148.169.247` |
| `SMALL_USER` | `ubuntu` |
| `SMALL_SSH_KEY` | 小站私钥全文 |
| `SMALL_DEPLOY_PATH` | `/home/ubuntu/gptsignup`（可选） |
| `SMALL_PORT` | `22`（可选） |

### 3. 自动更新

```text
git push origin main
  → GitHub Actions deploy-small
  → SSH 小站
  → deploy/deploy.sh
```

执行：

```bash
cd ~/gptsignup
docker compose --profile tools run --rm gptsignup --yes -w 3 -n 1
```

## 与 Grok 差异

| 项 | Grok | 本项目 |
|---|---|---|
| 凭据 | `sso` | `accessToken`（`/api/auth/session`） |
| 输出 | `keys/grok_*` | `keys/gpt_*` + `*_accounts.txt` |
| 邮箱 | CF Temp Mail | Outlook Email Plus 邮箱池 |

## 注意事项

1. `.env` 永不提交；服务器上单独维护。
2. 池空会报 `NO_AVAILABLE_ACCOUNT`：先在 OEP 导入账号。
3. `registration_disallowed` 多为邮箱域名/IP 风控，换池内账号或代理。
4. Codex 路径可能强制 `add_phone`；默认 platform client 走 `about_you`。
5. 仅供学习研究。
