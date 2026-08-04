# Codex Reset Reminder

监控 [OpenAI Codex](https://openai.com/index/codex/) 工程师 Tibo（[@thsottiaux](https://x.com/thsottiaux)）的 X 推文，当他宣布重置 Codex 使用额度时，第一时间通过飞书机器人和微信推送提醒。

## 工作流程

```
GitHub Actions (每 5 分钟)
    → Python 脚本拉取 RSSHub RSS
    → 去重（对比 sent_tweets.json）
    → DeepSeek 语义分类 + "reset" 关键词兜底
    → 命中即推送飞书 + 微信
    → 更新 sent_tweets.json 并 commit 回仓
```

## 推送判定逻辑

双保险机制，任一命中即推送：

- **LLM 语义分析**：DeepSeek-v4-flash 判断推文是否与 Codex 额度 reset 相关（明确/暗示/无关）
- **关键词兜底**：推文文本中只要出现 "reset" 字样就一定推送，防止 LLM 漏判

## 项目结构

```
├── .github/workflows/poll.yml   # GitHub Actions 定时任务
├── src/
│   ├── main.py                  # 主流程
│   ├── rsshub_client.py         # RSSHub RSS 拉取
│   ├── deduper.py               # 去重持久化
│   ├── classifier.py            # DeepSeek 分类
│   ├── feishu_pusher.py         # 飞书推送
│   ├── wechat_pusher.py         # 微信推送（Server酱）
│   └── test_local.py            # 本地测试脚本
├── render.yaml                  # Render 部署配置
├── requirements.txt
└── .env.example                 # 环境变量模板
```

## 技术栈

- **数据源**：[RSSHub](https://github.com/DIYgod/RSSHub) 自建实例（部署在 Render 免费档，海外节点免梯子）
- **调度**：GitHub Actions（每 5 分钟 cron）
- **语义分析**：DeepSeek-v4-flash API
- **推送**：飞书自定义机器人 webhook（群内可见）+ Server酱微信推送（仅个人接收）
- **去重持久化**：`sent_tweets.json` + git commit 回仓
