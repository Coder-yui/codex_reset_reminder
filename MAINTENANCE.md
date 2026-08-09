# 日常维护

## X Cookie 失效

Actions 日志出现登录、401、403、404 或无可用账号错误时：

1. 在浏览器登录 `https://x.com`。
2. 打开开发者工具 → Application → Cookies → `https://x.com`。
3. 复制 `auth_token` 和 `ct0`。
4. 更新 GitHub Actions Secrets `TWITTER_AUTH_TOKEN`、`TWITTER_CT0`。
5. 手动运行一次 `Poll Tibo Reset` 验证。

## 通知失败

- 飞书：检查 `FEISHU_WEBHOOK_URL`。
- 微信：检查 `SERVERCHAN_KEY` 和 Server酱当日额度。

命中 reset 的帖子只有至少一个通知渠道成功后才会写入去重记录；全部失败时下轮会重试。
