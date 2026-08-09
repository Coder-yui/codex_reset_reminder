"""去重：基于本地 sent_tweets.json 文件记录已处理的推文 id"""
import json
import os
from typing import List, Dict, Set


def load_sent(path: str) -> Set[str]:
    """加载已处理过的推文 id 集合"""
    if not os.path.exists(path):
        return set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return set(data.get("sent_ids", []))
    except (json.JSONDecodeError, IOError):
        return set()


def save_sent(path: str, sent_ids: Set[str], max_keep: int = 1000) -> None:
    """
    持久化已处理 id 集合。

    Args:
        max_keep: 最多保留多少条 id，防止文件无限增长。
    """
    ids_list = list(sent_ids)
    if len(ids_list) > max_keep:
        ids_list = ids_list[-max_keep:]
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"sent_ids": ids_list}, f, ensure_ascii=False, indent=2)


def filter_new(tweets: List[Dict], sent_ids: Set[str]) -> List[Dict]:
    """过滤出尚未处理过的新推文"""
    return [t for t in tweets if t["id"] and t["id"] not in sent_ids]
