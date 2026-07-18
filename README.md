# ChatGPT 注册 + Sub2API 导入

流程：

```text
chatgpt.com → Login → 邮箱 OTP → Full Name/Age
  → 保持浏览器登录态
  → https://api4kimi8.org/admin/accounts 添加账号
  → 平台 OpenAI → 手动授权 → 生成授权链接
  → 同浏览器打开链接 → Tiger SMS 手机验证
  → 回填授权码完成导入
```

**accessToken 可选**，成功以 Sub2API 导入为准。

## 环境变量

| 变量 | 说明 |
|------|------|
| `OEP_*` | Outlook Email Plus 邮箱池 |
| `SUB2API_BASE_URL` | 默认 `https://api4kimi8.org` |
| `SUB2API_ADMIN_EMAIL` / `SUB2API_ADMIN_PASSWORD` | 管理端登录 |
| `TIGER_SMS_API_KEY` | Tiger SMS v2 |
| `TIGER_SMS_SERVICE` | 默认 `dr` |
| `TIGER_SMS_COUNTRY` | 默认 `1001` |
| `PROXY` | Playwright 代理 |
| `BROWSER_HEADLESS` | 默认 `0`（有头） |

## 本机运行

```bash
cd ~/Desktop/gptsignup
source .venv/bin/activate
pip install -r requirements.txt
playwright install chrome

# .env 至少填：OEP_*、SUB2API_ADMIN_*、TIGER_SMS_API_KEY
export BROWSER_HEADLESS=0
export BROWSER_CHANNEL=chrome
export PROXY=http://127.0.0.1:6152   # 按需

python chatgpt.py --yes -w 1 -n 1
```

## 输出

```text
keys/gpt_*_accounts.txt   # email|passwordless|token或no-token
keys/gpt_*.txt            # 仅当取到 accessToken 时写入
```

## 注意

1. 并发保持 **1**（浏览器 + 管理端 + 短信）。
2. OAuth 与 ChatGPT 必须同一浏览器 context（代码已 `new_page` 共享 cookie）。
3. 手机号填 **不带国家码** 的 national number（Tiger `national_number`）。
4. 仅供学习研究。
