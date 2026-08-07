#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""translate.py —— 翻译层。读 ../data.js，翻译非中文新闻的标题+全文，写回 data.js。
- zh: 中文标题
- content_zh: 中文全文摘要（300字内）
已有翻译的跳过（支持增量补翻）。
"""
import json, os, re
from concurrent.futures import ThreadPoolExecutor
import llm

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WORKERS = 3
ATTEMPTS = 2
BATCH = 3            # 每批翻译 N 条

SYS = ("你是中文翻译助手。给你若干条英文新闻(每条带序号、标题、正文)，翻译成中文。\n"
       "要求：1) 标题翻译准确简洁；2) 正文翻译为 300 字内的摘要，保留关键信息和数据。\n"
       "只输出 JSON,不要任何解释或代码块标记。格式:\n"
       '{"items":[{"i":0,"zh":"中文标题","czh":"中文正文摘要"}]}')

CFG = {"provider": "claude-cli"}


def is_cjk(text):
    if not text:
        return False
    sample = text[:300]
    cjk = sum(1 for c in sample if '\u4e00' <= c <= '\u9fff' or '\u3040' <= c <= '\u30ff')
    return cjk / max(len(sample), 1) > 0.3


def _llm(user, label=""):
    try:
        return llm.call(SYS, user, CFG)
    except Exception as e:
        print("  ⚠️ LLM 调用异常 [%s]: %s" % (label, str(e)[:120]))
        return ""


def extract_json(s):
    if not s:
        return None
    a, b = s.find("{"), s.rfind("}")
    if a < 0 or b < 0:
        return None
    try:
        return json.loads(s[a:b + 1])
    except Exception:
        return None


def translate_batch(batch_items, label=""):
    """翻译一批新闻。返回 {index: {"zh":..., "czh":...}}"""
    lines = []
    for i, it in enumerate(batch_items):
        title = it.get("title", "")
        content = (it.get("content") or it.get("summary") or "")[:1200]
        lines.append("[%d] 标题：%s\n正文：%s" % (i, title, content))
    user = "\n\n".join(lines)
    for _ in range(ATTEMPTS):
        d = extract_json(_llm(user, label))
        if d and isinstance(d.get("items"), list):
            result = {}
            for x in d["items"]:
                if isinstance(x, dict) and "i" in x:
                    result[x["i"]] = {"zh": x.get("zh", ""), "czh": x.get("czh", "")}
            return result
    return {}


def main():
    global CFG
    CFG = llm.load_config(ROOT)
    print("大模型 provider:", CFG.get("provider", "claude-cli"))
    p = os.path.join(ROOT, "data.js")
    txt = open(p, encoding="utf-8").read()
    data = json.loads(txt[txt.index("{"):txt.rindex("}") + 1])

    # 收集所有需翻译的条目（非中文 + 无 zh）
    tasks = []  # (item_ref, ind_name)
    for ind in data["industries"]:
        for it in ind.get("items", []):
            title = it.get("title", "")
            if is_cjk(title):
                # 中文源：zh 用原标题，content_zh 用原 content
                if not it.get("zh"):
                    it["zh"] = title
                if not it.get("content_zh") and it.get("content"):
                    it["content_zh"] = it["content"][:300]
                continue
            if it.get("zh") and it.get("content_zh"):
                continue  # 已翻译
            tasks.append((it, ind["name"]))

    total = len(tasks)
    print("需翻译 %d 条（非中文且缺翻译）" % total)
    if not total:
        print("无需翻译")
        return

    done = 0
    # 分批
    batches = [tasks[i:i + BATCH] for i in range(0, total, BATCH)]

    def do_batch(batch):
        items = [t[0] for t in batch]
        label = batch[0][1]
        result = translate_batch(items, label)
        for i, it in enumerate(items):
            if i in result:
                if result[i]["zh"]:
                    it["zh"] = result[i]["zh"]
                if result[i]["czh"]:
                    it["content_zh"] = result[i]["czh"]
        return len(result)

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for cnt in ex.map(do_batch, batches):
            done += cnt
            if done % 30 == 0 or done == total:
                print("  进度: %d/%d" % (done, total))

    # 写回
    with open(p, "w", encoding="utf-8") as f:
        f.write("// data.js —— 含翻译。\n")
        f.write("window.DATA = " + json.dumps(data, ensure_ascii=False, indent=1) + ";\n")

    # 统计
    zh_cnt = czh_cnt = 0
    for ind in data["industries"]:
        for it in ind.get("items", []):
            if it.get("zh"):
                zh_cnt += 1
            if it.get("content_zh"):
                czh_cnt += 1
    print("翻译完成：标题 %d 条，全文 %d 条" % (zh_cnt, czh_cnt))


if __name__ == "__main__":
    main()
