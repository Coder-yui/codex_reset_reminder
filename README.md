# Codex Reset Reminder

每 5 分钟读取 Tibo（[@thsottiaux](https://x.com/thsottiaux)）的 X 时间线。新帖子正文包含 `reset` 时，推送到飞书和微信。

## 流程

```text
twscrape UserTweetsAndReplies
  → sent_tweets.json 去重
  → reset 关键词匹配
  → 飞书 + Server酱微信
```

项目只使用一个 X 抓取方法，不包含 RSSHub、Nitter/XCancel、搜索接口、单条补发或 LLM 分类。

## 配置

在 GitHub Actions Secrets 中配置：

- `TWITTER_AUTH_TOKEN`：登录 X 后的 `auth_token` Cookie
- `TWITTER_CT0`：登录 X 后的 `ct0` Cookie
- `FEISHU_WEBHOOK_URL`：飞书自定义机器人 Webhook
- `SERVERCHAN_KEY`：Server酱 SendKey
- `TWITTER_USERNAME`：可选，默认 `thsottiaux`
- `TWITTER_USER_ID`：可选，默认 Tibo 的用户 ID

推送到 `main` 后会立即执行一次，之后 GitHub Actions 每 5 分钟运行。

## 本地运行

```bash
cp .env.example .env
python -m venv venv
venv/bin/pip install -r requirements.txt
venv/bin/python src/main.py
```

X Cookie 失效后，从浏览器重新复制 `auth_token` 和 `ct0` 并更新 Secrets。
