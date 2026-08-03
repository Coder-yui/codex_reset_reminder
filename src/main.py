"""主流程：拉取 → 去重 → 分类 → 推送 → 持久化"""
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

    # 3. 分类 + 推送
    print("[3/4] 分类并推送...")
    pushed = 0
    for t in new_tweets:
        try:
            result = classify(t, deepseek_key, deepseek_model)
        except Exception as e:
            print(f"  [WARN] 分类失败 {t['id']}: {e}")
            # 分类失败也算处理过，避免下次重复尝试同一条
            sent_ids.add(t["id"])
            continue

        cat = result.get("category", 3)
        conf = result.get("confidence", 0)
        reason = result.get("reason", "")

        if cat in (1, 2) and conf >= threshold:
            label = "明确宣布" if cat == 1 else "暗示即将"
            title = f"Tibo {label} Codex 额度 Reset（置信度 {conf:.2f}）"
            content = f"{t.get('title', '')}\n\n分类原因：{reason}"
            if feishu_webhook:
                ok = feishu_push(feishu_webhook, title, content, t.get("link", ""))
                print(f"  推送 {t['id']}: cat={cat} conf={conf:.2f} -> {'OK' if ok else 'FAIL'}")
                if ok:
                    pushed += 1
            else:
                print(f"  [SKIP推送，未配 webhook] {t['id']}: cat={cat} conf={conf:.2f} ({reason})")
        else:
            print(f"  跳过 {t['id']}: cat={cat} conf={conf:.2f} ({reason})")

        # 无论是否推送，都标记为已处理
        sent_ids.add(t["id"])

    # 4. 持久化
    print("[4/4] 保存已处理记录...")
    save_sent(str(SENT_FILE), sent_ids)
    print(f"[完成] 推送 {pushed} 条，共处理 {len(new_tweets)} 条新推文")


if __name__ == "__main__":
    main()
