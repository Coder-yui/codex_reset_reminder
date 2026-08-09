# Codex Reset Reminder

监控 [OpenAI Codex](https://openai.com/index/codex/) 工程师 Tibo（[@thsottiaux](https://x.com/thsottiaux)）的 X 推文，当他宣布重置 Codex 使用额度时，第一时间通过飞书机器人和微信推送提醒。

## 工作流程

```
GitHub Actions (每 5 分钟)
    → 并行读取 RSSHub + XCancel 公开主页，按帖子 ID 取并集
    → 去重（对比 sent_tweets.json）
    → "reset" 关键词立即判定；未命中时再做 DeepSeek 语义分类
    → 命中即推送飞书 + 微信
    → 更新 sent_tweets.json 并 commit 回仓
```

## 推送判定逻辑

双保险机制，任一命中即推送：

- **关键词快速通道**：推文文本中出现 "reset" 就立即推送，不等待也不调用 LLM
- **LLM 语义分析**：未出现关键词时，DeepSeek-v4-flash 判断是否用其他表达宣布或暗示 reset；未配置 API Key 时自动退化为免费关键词模式

## 项目结构

```
├── .github/workflows/poll.yml   # GitHub Actions 定时任务
├── src/
│   ├── main.py                  # 主流程
│   ├── rsshub_client.py         # RSSHub RSS 拉取
│   ├── xcancel_client.py        # XCancel 公开主页解析
│   ├── multi_source_client.py   # 双源并行读取、容错和合并
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

- **数据源**：[RSSHub](https://github.com/DIYgod/RSSHub) 自建实例 + [XCancel](https://xcancel.com) 公开主页；任一成功即可继续
- **调度**：GitHub Actions（每 5 分钟 cron）
- **语义分析**：DeepSeek-v4-flash API
- **推送**：飞书自定义机器人 webhook（群内可见）+ Server酱微信推送（仅个人接收）
- **去重持久化**：`sent_tweets.json` + git commit 回仓

## 数据源容错

RSSHub 和 XCancel 会并行请求。两边的帖子按数字 ID 取并集，重复帖子只处理一次；某一个来源超时或页面异常时，另一个来源仍会继续工作。只有两个来源同时失败，任务才会以拉取失败结束。
