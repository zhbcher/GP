"""Feishu webhook notification service.

Sends alert notifications to a Feishu group chat via incoming webhook.
Failures are silently ignored to avoid impacting the main alert flow.
"""
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)


def _get_webhook_url() -> str:
    """Read FEISHU_WEBHOOK_URL from env."""
    return os.environ.get("FEISHU_WEBHOOK_URL", "").strip()


async def send_feishu_message(text: str) -> None:
    """Send a simple text message to Feishu webhook. Silently fails."""
    url = _get_webhook_url()
    if not url:
        return
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.post(url, json={
                "msg_type": "text",
                "content": {"text": text},
            })
            if resp.status_code != 200:
                logger.warning(f"Feishu webhook returned {resp.status_code}: {resp.text}")
    except Exception as e:
        logger.warning(f"Feishu webhook failed: {e}")


async def notify_alert_triggered(
    stock_name: str,
    stock_code: str,
    alert_type: str,
    trigger_value: str,
    current_price: float,
    direction: str = "",
    extra_info: str = "",
) -> None:
    """Send a card-style alert notification to Feishu."""
    url = _get_webhook_url()
    if not url:
        return

    type_labels = {
        "price": "目标价预警",
        "change_pct": "涨跌幅预警",
        "volume": "放量预警",
    }
    type_label = type_labels.get(alert_type, alert_type)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        import httpx
        card = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": f"⚠️ {type_label} - {stock_name}({stock_code})"},
                    "template": "red",
                },
                "elements": [
                    {"tag": "div", "text": {"tag": "lark_md", "content": f"**触发条件**: {trigger_value}"}},
                    {"tag": "div", "text": {"tag": "lark_md", "content": f"**当前价格**: {current_price:.2f}"}},
                ],
            },
        }
        if extra_info:
            card["card"]["elements"].append(
                {"tag": "div", "text": {"tag": "lark_md", "content": f"**详情**: {extra_info}"}}
            )
        card["card"]["elements"].append(
            {"tag": "div", "text": {"tag": "lark_md", "content": f"**触发时间**: {now_str}"}}
        )

        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.post(url, json=card)
            if resp.status_code != 200:
                logger.warning(f"Feishu webhook returned {resp.status_code}: {resp.text}")
    except Exception as e:
        logger.warning(f"Feishu webhook failed: {e}")
