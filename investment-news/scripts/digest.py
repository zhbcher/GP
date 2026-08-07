#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""digest.py —— AI 要点层。读 ../data.js，对每个行业生成 3-5 条中文「今日要点」，写回 data.js。
保留全部条目（不截断）；标题/全文翻译交给 translate.py。
"""
import json, os, re
from concurrent.futures import ThreadPoolExecutor
import llm

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TOPN = 16            # 每行业取最新 N 条做要点
WORKERS = 3
ATTEMPTS = 3
SYS = ("你是中文行业新闻分析助手。给你某行业最近的新闻列表(每条带序号),请提炼 3-5 条「今日要点」:"
       "聚合最重要的行业动向,每条不超过 40 字,可合并同类、突出数字/公司/趋势,客观陈述。"
       "每条要点用 refs 标注它主要来自哪几条新闻的序号(用于跳转原文,至少 1 个)。\n"
       "只输出 JSON,不要任何解释或代码块标记。格式:\n"
       '{"points":[{"t":"要点1","refs":[0,3]},{"t":"要点2","refs":[5]}]}')

CFG = {"provider": "claude-cli"}


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


def process(ind):
    if ind.get("points"):
        return ind  # 已有要点则跳过
    all_items = ind.get("items", [])
    top = all_items[:TOPN]
    if not top:
        ind["points"] = []
        return ind
    lines = ["行业:%s" % ind["name"], "新闻:"]
    for i, it in enumerate(top):
        # 优先用中文标题，否则用原标题
        title = it.get("zh") or it.get("title", "")
        lines.append("%d. %s (%s)" % (i, title, it.get("source", "")))
    user = "\n".join(lines)
    d = None
    for _ in range(ATTEMPTS):
        d = extract_json(_llm(user, ind["name"]))
        if d:
            break
    if not d:
        print("  ⚠️ %s 要点生成失败(已试 %d 次)" % (ind["name"], ATTEMPTS))
        ind["points"] = []
        return ind
    pts = []
    for p in d.get("points", [])[:5]:
        if isinstance(p, dict):
            t = (p.get("t") or "").strip()
            url = ""
            for r in p.get("refs", []):
                if isinstance(r, int) and 0 <= r < len(top) and top[r].get("url"):
                    url = top[r]["url"]
                    break
            if t:
                pts.append({"t": t, "url": url})
        elif isinstance(p, str) and p.strip():
            pts.append({"t": p.strip(), "url": ""})
    ind["points"] = pts
    return ind


def main():
    global CFG
    CFG = llm.load_config(ROOT)
    print("大模型 provider:", CFG.get("provider", "claude-cli"))
    p = os.path.join(ROOT, "data.js")
    txt = open(p, encoding="utf-8").read()
    data = json.loads(txt[txt.index("{"):txt.rindex("}") + 1])
    inds = data["industries"]
    print("对 %d 个行业生成 AI 要点(%d 并发)…" % (len(inds), WORKERS))
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        list(ex.map(process, inds))
    data["has_ai"] = True
    with open(p, "w", encoding="utf-8") as f:
        f.write("// data.js —— 含 AI 要点。\n")
        f.write("window.DATA = " + json.dumps(data, ensure_ascii=False, indent=1) + ";\n")
    for ind in inds:
        n = len(ind.get("points", []))
        print("  %-16s 要点 %d 条 · 条目 %d" % (ind["name"], n, len(ind.get("items", []))))


if __name__ == "__main__":
    main()
