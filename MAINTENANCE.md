# 日常维护

## X Cookie 过期更新（约 1-3 个月一次）

RSSHub 依赖你的 X cookie 拉取推文，cookie 会定期失效。

**症状**：Actions 日志出现拉取失败，或返回的推文数为 0。

**步骤**：
1. 浏览器登录 https://x.com
2. F12 → Application → Cookies → `https://x.com`
3. 复制 `auth_token` 和 `ct0` 的 Value
4. 去 Render Dashboard → 你的 RSSHub 服务 → Environment
5. 更新 `TWITTER_AUTH_TOKEN` 和 `TWITTER_CT0` 两个变量
6. 保存后会自动重新部署

## Actions 异常排查

去 https://github.com/Coder-yui/codex_reset_reminder/actions 查看运行记录。

| 现象 | 可能原因 | 处理 |
|---|---|---|
| `Commit sent_tweets.json` 步骤失败 | 并发触发冲突，已用 `continue-on-error` 兜底，不影响推送 | 可忽略 |
| `Run poll` 步骤失败 | RSSHub 挂了 / DeepSeek 余额不足 / 飞书 webhook 失效 | 看日志定位 |
| 推送数一直为 0 | Tibo 最近没发 reset 相关推文，正常 | 等待 |
| 拉取推文数为 0 | X cookie 过期 | 按上面步骤更新 |

## DeepSeek 余额

每次分类调用约 ¥0.001，月成本通常 < ¥1。
查看余额：https://platform.deepseek.com/usage

## 飞书机器人 webhook 失效

如果 webhook 被误删或群解散，推送会失败但不报错（脚本只打印 FAIL）。
重建：飞书群 → 设置 → 群机器人 → 添加自定义机器人 → 复制新 webhook → 更新 GitHub Secret `FEISHU_WEBHOOK_URL`。

## Server酱微信推送失效

如果微信推送失败，检查：
1. SendKey 是否正确：GitHub Secret `SERVERCHAN_KEY`
2. Server酱额度是否用完：https://sct.ftqq.com/user 查看今日剩余条数
3. 微信公众号是否关注：需要关注"Server酱"公众号才能接收消息

如果 SendKey 泄露或需要更换：
1. 去 https://sct.ftqq.com 重新生成 SendKey
2. 更新 GitHub Secret `SERVERCHAN_KEY`

## 本地测试

```bash
cp .env.example .env
# 填入 DEEPSEEK_API_KEY 和 FEISHU_WEBHOOK_URL
pip install -r requirements.txt
python src/test_local.py
```

会向飞书群发 4 条测试消息（含 reset 关键词和 LLM 判定各种场景），不写入 sent_tweets.json，可重复运行。
