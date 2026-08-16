"""数据源解析逻辑测试：sina/tencent/baidu 字段解析（用构造数据，不依赖网络）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.data_sources.a_stock_data import _strip_market_prefix, _load_tdx_servers
from app.data_sources.a_stock_data import fetch_tencent_kline_sync


def test_strip_market_prefix():
    assert _strip_market_prefix("sh600519") == "600519"
    assert _strip_market_prefix("sz000001") == "000001"
    assert _strip_market_prefix("bj430047") == "430047"
    assert _strip_market_prefix("600519") == "600519"


def test_tdx_servers_default():
    """默认服务器列表首位是已知可用服务器。"""
    servers = _load_tdx_servers()
    assert len(servers) >= 10
    assert servers[0] == ("218.75.126.9", 7709)


def test_tdx_servers_env_override(monkeypatch):
    """环境变量 TDX_SERVERS 可覆盖服务器列表。"""
    monkeypatch.setenv("TDX_SERVERS", "1.2.3.4:7709,5.6.7.8:8800")
    servers = _load_tdx_servers()
    assert servers == [("1.2.3.4", 7709), ("5.6.7.8", 8800)]


def test_tencent_kline_invalid_code():
    """无效代码返回空列表（不抛异常）。"""
    code, rows = fetch_tencent_kline_sync("sh000000")
    assert code == "sh000000"
    assert rows == []
