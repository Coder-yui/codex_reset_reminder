"""主流程：拉取 → 去重 → 分类 + 关键词兜底 → 推送 → 持久化"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# 让 main.py 既能被 `python src/main.py` 跑，也能被 `python -m src.main` 跑
sys.path.insert(0, str(Path(__file__).parent))

from rsshub_client import fetch_tweets
from deduper import load_sent, save_sent, filter_new
from classifier import classify
from feishu_pusher import push as feishu_push


SENT_FILE = Path(__file__).parent / "sent_tweets.json"


def contains_reset(tweet: dict) -> bool:
    """硬性关键词检测：推文标题或正文中是否出现 reset 字样（不区分大小写）。

    作为 LLM 分类的兜底，确保任何含 reset 的推文都不会被遗漏。
    """
    text = f"{tweet.get('title', '')} {tweet.get('summary', '')}".lower()
    return "reset" in text


def main():
    load_dotenv()

    rsshub_url = os.getenv("RSSHUB_URL")
    username = os.getenv("TWITTER_USERNAME", "thsottiaux")
    deepseek_key = os.getenv("DEEPSEEK_API_KEY")
    deepseek_model = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    feishu_webhook = os.getenv("FEISHU_WEBHOOK_URL")
    threshold = float(os.getenv("CONFIDENCE_THRESHOLD", "0.5"))

    if not rsshub_url:
        print("[ERROR] RSSHUB_URL 未配置")
        return
    if not deepseek_key:
        print("[ERROR] DEEPSEEK_API_KEY 未配置")
        return

    # 1. 拉取 RSS
    print(f"[1/4] 拉取 @{username} 的最近推文...")
    try:
        tweets = fetch_tweets(rsshub_url, username)
    except Exception as e:
        print(f"[ERROR] 拉取失败: {e}")
        return
    print(f"  共拉到 {len(tweets)} 条")

    # 2. 去重
    sent_ids = load_sent(str(SENT_FILE))
    new_tweets = filter_new(tweets, sent_ids)
    print(f"[2/4] 去重后新推文 {len(new_tweets)} 条")

    if not new_tweets:
        print("[完成] 无新推文")
        return

    # 3. 分类 + 关键词兜底 + 推送
    print("[3/4] 分类并推送...")
    pushed = 0
    for t in new_tweets:
        # LLM 分类（可能失败，但不影响关键词兜底）
        llm_result = None
        try:
            llm_result = classify(t, deepseek_key, deepseek_model)
        except Exception as e:
            print(f"  [WARN] LLM 分类失败 {t['id']}: {e}")

        # 关键词硬检测（永不遗漏）
        keyword_hit = contains_reset(t)

        # LLM 判定
        llm_push = False
        cat = conf = reason = None
        if llm_result:
            cat = llm_result.get("category", 3)
            conf = llm_result.get("confidence", 0)
            reason = llm_result.get("reason", "")
            if cat in (1, 2) and conf >= threshold:
                llm_push = True

        # 推送条件：LLM 判定 OR 关键词命中
        should_push = llm_push or keyword_hit

        if should_push:
            # 构造标签，标注是哪条线触发的推送
            if llm_push and keyword_hit:
                llm_label = "明确" if cat == 1 else "暗示"
                tag = f"LLM:{llm_label}({conf:.2f}) + 关键词命中"
            elif llm_push:
                llm_label = "明确" if cat == 1 else "暗示"
                tag = f"LLM:{llm_label}({conf:.2f})"
            else:
                # 关键词命中但 LLM 判无关（或 LLM 失败）
                tag = "关键词命中(LLM判无关)" if llm_result else "关键词命中(LLM失败)"

            title = f"Tibo Codex Reset 信号 [{tag}]"
            content = t.get("summary", "") or t.get("title", "")
            if reason:
                content += f"\n\nLLM 分析：{reason}"

            if feishu_webhook:
                ok = feishu_push(feishu_webhook, title, content, t.get("link", ""))
                print(f"  推送 {t['id']}: {tag} -> {'OK' if ok else 'FAIL'}")
                if ok:
                    pushed += 1
            else:
                print(f"  [SKIP推送，未配 webhook] {t['id']}: {tag}")
        else:
            conf_str = f"{conf:.2f}" if conf is not None else "N/A"
            print(f"  跳过 {t['id']}: cat={cat} conf={conf_str} ({reason or '无LLM分析'})")

        # 无论是否推送，都标记为已处理
        sent_ids.add(t["id"])

    # 4. 持久化
    print("[4/4] 保存已处理记录...")
    save_sent(str(SENT_FILE), sent_ids)
    print(f"[完成] 推送 {pushed} 条，共处理 {len(new_tweets)} 条新推文")


if __name__ == "__main__":
    main()
