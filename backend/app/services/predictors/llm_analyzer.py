"""PRED-011: LLM 分析报告 — 把 K线摘要 + 各模型结果压成文本，调 LLM 生成中文分析。

复用 .env 的 NEWS_AI_API_KEY / NEWS_AI_BASE_URL / NEWS_AI_MODEL（OpenAI 兼容接口）。
按 (stock_code, date) 缓存到 ~/GP/data/predict_llm_cache.json，当天不重复调用。
超时/失败时降级返回 status=error，不影响主预测流程。
"""
import asyncio
import json
import logging
import os
from datetime import datetime

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

CACHE_PATH = os.path.expanduser("~/GP/data/predict_llm_cache.json")
TIMEOUT = 180
MAX_REPORTS = 200  # 缓存条目上限，超出裁剪最旧


def _load_cache() -> dict:
    try:
        with open(CACHE_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cache(cache: dict):
    try:
        if len(cache) > MAX_REPORTS:
            keys = sorted(cache.keys())
            for k in keys[: len(cache) - MAX_REPORTS]:
                cache.pop(k, None)
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        with open(CACHE_PATH, "w") as f:
            json.dump(cache, f, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"llm cache save failed: {e}")


def _build_prompt(code: str, name: str, kline_summary: str, models: dict, ensemble: dict) -> str:
    model_lines = []
    tech = models.get("technical") or {}
    if tech.get("signals"):
        sig = tech["signals"]
        model_lines.append(f"- 技术指标: 趋势={tech.get('trend')} 置信度={tech.get('confidence')} MA信号={sig.get('ma')} MACD={sig.get('macd')} RSI={sig.get('rsi')} KDJ={sig.get('kdj')}")
    stat = models.get("statistical") or {}
    if stat.get("forecast"):
        model_lines.append(f"- 统计模型: 趋势={stat.get('trend')} 5日后目标价={stat['forecast'][-1].get('price')}")
    mc = models.get("monte_carlo") or {}
    if mc.get("median"):
        model_lines.append(f"- 蒙特卡洛: 中位价={mc.get('median')} 区间[{mc.get('range_low')},{mc.get('range_high')}] 上涨概率={mc.get('up_probability')}")
    pat = models.get("patterns") or {}
    if pat.get("patterns"):
        pats = ", ".join(f"{p.get('type')}({p.get('direction')})" for p in pat["patterns"][:3])
        model_lines.append(f"- 形态识别: {pats}")
    ml = models.get("ml") or {}
    if ml.get("up_probability") is not None:
        model_lines.append(f"- XGBoost: 上涨概率={ml.get('up_probability')} 信号={ml.get('signal')}")
    dl = models.get("deep_learning") or {}
    if dl.get("forecast"):
        model_lines.append(f"- LSTM: 5日后目标价={dl['forecast'][-1].get('price')} 方向准确率={dl.get('direction_accuracy')}")
    en = ensemble or {}
    model_lines.append(f"- 融合结论: {en.get('final_trend')} 置信度={en.get('weighted_confidence')} 目标价={en.get('target_price')}")

    return f"""你是资深 A 股分析师。根据以下量化模型输出，为股票 {name}({code}) 写一份简短的中文分析报告。

## 近期走势
{kline_summary}

## 各模型结论
{chr(10).join(model_lines)}

## 输出要求（严格按此 JSON 输出，不要输出其它内容）:
{{
  "summary": "3-4句话的走势与逻辑总结（客观描述模型分歧与共识）",
  "suggestion": "一句话操作建议（看多/看空/观望 + 理由，必须提示模型预测存在不确定性）",
  "risk": "1-2条当前主要风险点",
  "confidence": 0-100 的整数, 表示你对该判断的把握
}}"""


async def analyze_with_llm(code: str, name: str, kline_summary: str,
                           models: dict, ensemble: dict,
                           use_cache: bool = True) -> dict:
    settings = get_settings()
    api_key = getattr(settings, "news_ai_api_key", None) or os.getenv("NEWS_AI_API_KEY")
    base_url = getattr(settings, "news_ai_base_url", None) or os.getenv("NEWS_AI_BASE_URL", "")
    model = getattr(settings, "news_ai_model", None) or os.getenv("NEWS_AI_MODEL", "")

    if not api_key or not base_url:
        return {"status": "not_configured", "summary": "", "suggestion": "", "risk": ""}

    today = datetime.now().strftime("%Y-%m-%d")
    cache_key = f"{code}:{today}"
    cache = _load_cache()
    if use_cache and cache_key in cache:
        hit = dict(cache[cache_key])
        hit["cached"] = True
        return hit

    prompt = _build_prompt(code, name, kline_summary, models, ensemble)

    try:
        import time as _time
        _t0 = _time.time()
        logger.info(f"llm POST start for {code}, timeout={TIMEOUT}")
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(
                base_url.rstrip("/") + "/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "max_tokens": 4000,  # 推理模型先消耗token思考，800会截断导致content为空
                },
            )
            logger.info(f"llm POST done for {code} in {_time.time()-_t0:.1f}s, http={resp.status_code}")
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"].get("content")
        if not content:
            return {"status": "error", "summary": "", "suggestion": "", "risk": "", "error": "empty_response(可能因token限制被截断)"}

        # 提取 JSON（容忍 ```json 包裹）
        text = content.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        parsed = json.loads(text)

        result = {
            "status": "ok",
            "summary": parsed.get("summary", ""),
            "suggestion": parsed.get("suggestion", ""),
            "risk": parsed.get("risk", ""),
            "confidence": parsed.get("confidence", 50),
            "date": today,
        }
        cache[cache_key] = result
        _save_cache(cache)
        return result
    except json.JSONDecodeError as e:
        logger.warning(f"llm parse failed for {code}: {e}")
        return {"status": "error", "summary": "", "suggestion": "", "risk": "", "error": "parse_error"}
    except Exception as e:
        logger.warning(f"llm analyze failed for {code}: {type(e).__name__}: {e}")
        return {"status": "error", "summary": "", "suggestion": "", "risk": "", "error": str(e)[:200]}
