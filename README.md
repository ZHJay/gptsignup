# ChatGPT 批量注册工具

基于 `grokzhuce` 架构：自动注册 ChatGPT / OpenAI 账号，并在**同一 HTTP session** 内打开：

```text
https://chatgpt.com/api/auth/session
```

提取 `accessToken`（相对 Grok 的 `sso`）。

## 快速开始（本地）

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # 填邮箱服务
python chatgpt.py                  # 交互
python chatgpt.py --yes -w 3 -n 5  # 非交互
```

## Docker（小站推荐）

```bash
# 首次：准备 .env 与 keys
cp .env.example .env && chmod 600 .env
mkdir -p keys && chmod 700 keys

docker compose build
docker compose --profile tools run --rm gptsignup --yes -w 3 -n 1
```

环境变量（可选）：

| 变量 | 说明 |
|------|------|
| `MAIL_*` | 临时邮箱（见 `.env.example`） |
| `PROXY` | 代理 |
| `GPT_WORKERS` | 默认并发 |
| `GPT_TOTAL` | 默认注册数量 |

输出挂载：`./keys` → 容器 `/app/keys`。

## 小站部署与 push 自动更新

路径约定：`ubuntu@小站:~/gptsignup`

### 1. 服务器 bootstrap（一次性）

```bash
# 保留已有 .env，用 Git 接管目录
cd ~
mv gptsignup gptsignup.bak 2>/dev/null || true
git clone https://github.com/ZHJay/gptsignup.git gptsignup
cp gptsignup.bak/.env gptsignup/.env
chmod 600 gptsignup/.env
mkdir -p gptsignup/keys && chmod 700 gptsignup/keys
cd gptsignup
bash deploy/deploy.sh
```

### 2. GitHub Secrets（仓库 Settings → Secrets）

| Secret | 示例 |
|--------|------|
| `SMALL_HOST` | `141.148.169.247` |
| `SMALL_USER` | `ubuntu` |
| `SMALL_SSH_KEY` | 小站私钥全文 |
| `SMALL_DEPLOY_PATH` | `/home/ubuntu/gptsignup`（可选） |
| `SMALL_PORT` | `22`（可选） |

### 3. 自动更新流程

```text
git push origin main
  → GitHub Actions deploy-small
  → SSH 小站
  → deploy/deploy.sh
      git fetch + reset --hard origin/main
      docker compose build → 镜像 gptsignup:latest
```

每次 push 后镜像即为最新；执行：

```bash
cd ~/gptsignup
docker compose --profile tools run --rm gptsignup --yes -w 3 -n 1
```

手动触发：GitHub Actions → `deploy-small` → Run workflow。

## 与 Grok 差异

| 项 | Grok | 本项目 |
|---|---|---|
| 凭据 | `sso` | `accessToken`（`/api/auth/session`） |
| 输出 | `keys/grok_*` | `keys/gpt_*` + `*_accounts.txt` |

## 注意事项

1. `.env` 永不提交；服务器上单独维护。
2. `registration_disallowed` 多为邮箱域名/IP 风控，换 `MAIL_DOMAIN` 或代理。
3. Codex 路径可能强制 `add_phone`；默认 platform client 走 `about_you`。
4. 仅供学习研究。
