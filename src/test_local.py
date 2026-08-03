"""
本地测试脚本：不依赖 RSSHub，用模拟推文验证 DeepSeek 分类 + 飞书推送链路。

用法：
    cp .env.example .env  # 填好 DEEPSEEK_API_KEY 和 FEISHU_WEBHOOK_URL
    pip install -r requirements.txt
    python src/test_local.py

会做三件事：
1. 调用 DeepSeek 对 5 条模拟推文分类，打印结果
2. 对分类为 1/2 的推文，真实推送一条到飞书群
3. 不写入 sent_tweets.json，可重复运行
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))

from classifier import classify
from feishu_pusher import push as feishu_push


# 5 条模拟推文，覆盖三种情况
# 其中前 3 条参考了搜索到的 Tibo 真实表达风格
MOCK_TWEETS = [
    {
        "id": "mock-1-explicit-reset",
        "title": "Tibo",
        "summary": "We've reset everyone's Codex usage limits back to 100%. Sorry for the issues earlier today, enjoy the fresh quota.",
        "link": "https://x.com/thsottiaux/status/mock1",
        "published": "2026-08-03T10:00:00Z",
    },
    {
        "id": "mock-2-implicit-reset",
        "title": "Tibo",
        "summary": "Seeing the rate limit issues many of you are hitting. Looking into it now — if this continues we'll likely do a full reset later today.",
        "link": "https://x.com/thsottiaux/status/mock2",
        "published": "2026-08-03T11:00:00Z",
    },
    {
        "id": "mock-3-implicit-reworded",
        "title": "Tibo",
        "summary": "Heads up: all Codex quotas have been topped up. Limits are back to full. Shouldn't have drained that fast, investigating the bug.",
        "link": "https://x.com/thsottiaux/status/mock3",
        "published": "2026-08-03T12:00:00Z",
    },
    {
        "id": "mock-4-unrelated-feature",
        "title": "Tibo",
        "summary": "Codex now supports parallel subagents natively. You can spawn up to 5 concurrent tasks in a single session. Try it out!",
        "link": "https://x.com/thsottiaux/status/mock4",
        "published": "2026-08-03T13:00:00Z",
    },
    {
        "id": "mock-5-unrelated-personal",
        "title": "Tibo",
        "summary": "Beautiful sunset over SF today.",
        "link": "https://x.com/thsottiaux/status/mock5",
        "published": "2026-08-03T14:00:00Z",
    },
]


def main():
    load_dotenv()

    api_key = os.getenv("DEEPSEEK_API_KEY")
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    feishu_webhook = os.getenv("FEISHU_WEBHOOK_URL")
    threshold = float(os.getenv("CONFIDENCE_THRESHOLD", "0.5"))

    if not api_key:
        print("[ERROR] .env 里 DEEPSEEK_API_KEY 没填")
        sys.exit(1)
    if not feishu_webhook:
        print("[ERROR] .env 里 FEISHU_WEBHOOK_URL 没填")
        sys.exit(1)

    print(f"=== 本地测试 ===")
    print(f"模型: {model}")
    print(f"置信度阈值: {threshold}")
    print(f"飞书 webhook: {feishu_webhook[:60]}...")
    print(f"模拟推文: {len(MOCK_TWEETS)} 条\n")

    pushed = 0
    for i, t in enumerate(MOCK_TWEETS, 1):
        print(f"--- [{i}/{len(MOCK_TWEETS)}] {t['id']} ---")
        print(f"推文: {t['summary'][:80]}...")

        try:
            result = classify(t, api_key, model)
        except Exception as e:
            print(f"  [ERROR] 分类失败: {e}")
            continue

        cat = result.get("category", 3)
        conf = result.get("confidence", 0)
        reason = result.get("reason", "")
        cat_label = {1: "明确reset", 2: "暗示reset", 3: "无关"}[cat]
        print(f"  分类: {cat} ({cat_label})  置信度: {conf:.2f}")
        print(f"  原因: {reason}")

        if cat in (1, 2) and conf >= threshold:
            label = "明确宣布" if cat == 1 else "暗示即将"
            title = f"[测试] Tibo {label} Codex 额度 Reset（置信度 {conf:.2f}）"
            content = f"【测试推文，非真实事件】\n\n{t['summary']}\n\n分类原因：{reason}"
            ok = feishu_push(feishu_webhook, title, content, t.get("link", ""))
            print(f"  飞书推送: {'OK ✓' if ok else 'FAIL ✗'}")
            if ok:
                pushed += 1
        else:
            print(f"  跳过推送（cat={cat} 或 conf<{threshold}）")
        print()

    print(f"=== 测试完成 ===")
    print(f"共 {len(MOCK_TWEETS)} 条，推送 {pushed} 条到飞书")
    print(f"预期：mock-1/2/3 应触发推送（cat=1 或 2），mock-4/5 不推送（cat=3）")
    print(f"请检查飞书群是否收到 {pushed} 条测试消息")


if __name__ == "__main__":
    main()
