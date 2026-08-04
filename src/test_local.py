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


# 6 条模拟推文，覆盖各种情况
# mock-6 专门测试关键词兜底：含 reset 但语境无关额度，LLM 应判 cat=3，但关键词命中仍推送
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
    {
        "id": "mock-6-keyword-only-reset-env",
        "title": "Tibo",
        "summary": "Just reset my local dev environment to test the new build pipeline. Nothing production-related, just cleaning up configs.",
        "link": "https://x.com/thsottiaux/status/mock6",
        "published": "2026-08-03T15:00:00Z",
    },
]


def contains_reset(tweet: dict) -> bool:
    """硬性关键词检测，与 main.py 保持一致"""
    text = f"{tweet.get('title', '')} {tweet.get('summary', '')}".lower()
    return "reset" in text


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

        # LLM 分类（可能失败，但不影响关键词兜底）
        llm_result = None
        try:
            llm_result = classify(t, api_key, model)
        except Exception as e:
            print(f"  [ERROR] 分类失败: {e}")

        # 关键词硬检测
        keyword_hit = contains_reset(t)

        # LLM 判定
        llm_push = False
        cat = conf = reason = None
        if llm_result:
            cat = llm_result.get("category", 3)
            conf = llm_result.get("confidence", 0)
            reason = llm_result.get("reason", "")
            cat_label = {1: "明确reset", 2: "暗示reset", 3: "无关"}[cat]
            print(f"  分类: {cat} ({cat_label})  置信度: {conf:.2f}")
            print(f"  原因: {reason}")
        print(f"  关键词命中: {keyword_hit}")

        # 推送条件：LLM 判定 OR 关键词命中
        if llm_result and cat in (1, 2) and conf >= threshold:
            llm_push = True

        should_push = llm_push or keyword_hit

        if should_push:
            if llm_push and keyword_hit:
                llm_label = "明确" if cat == 1 else "暗示"
                tag = f"LLM:{llm_label}({conf:.2f}) + 关键词命中"
            elif llm_push:
                llm_label = "明确" if cat == 1 else "暗示"
                tag = f"LLM:{llm_label}({conf:.2f})"
            else:
                tag = "关键词命中(LLM判无关)" if llm_result else "关键词命中(LLM失败)"

            title = f"[测试] Tibo Codex Reset 信号 [{tag}]"
            content = f"【测试推文，非真实事件】\n\n{t['summary']}"
            if reason:
                content += f"\n\nLLM 分析：{reason}"
            ok = feishu_push(feishu_webhook, title, content, t.get("link", ""))
            print(f"  飞书推送: {'OK ✓' if ok else 'FAIL ✗'}  [{tag}]")
            if ok:
                pushed += 1
        else:
            print(f"  跳过推送（LLM判无关 且 无关键词）")
        print()

    print(f"=== 测试完成 ===")
    print(f"共 {len(MOCK_TWEETS)} 条，推送 {pushed} 条到飞书")
    print(f"预期：mock-1/2/3/6 应触发推送（含reset关键词或LLM判定）")
    print(f"      mock-4/5 不推送（无reset关键词且LLM判无关）")
    print(f"      mock-6 是关键测试：LLM 应判无关，但关键词命中仍推送")
    print(f"请检查飞书群是否收到 {pushed} 条测试消息")


if __name__ == "__main__":
    main()
