"""weather_server.py 的重试/缓存/结构化错误逻辑测试。

不需要真实 OPENWEATHER_API_KEY——用 `respx` 直接 mock OpenWeather 的 HTTP
响应，这条路径此前一直因为"没有真实 key"被搁置，其实跟 key 无关，
是这一轮回头补上的（用户直接问了"为什么不去完成"）。

`API_KEY` 和 `_cache` 都是 weather_server 模块级的全局变量，在模块导入时
就固定了，所以：
- 每个用例用不同的城市名，避免复用同一个进程内缓存导致的测试间串扰；
- 需要测试"没配 key"这个分支时，用 `importlib.reload` 重新加载模块。
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import httpx
import pytest
import respx

MCP_SERVERS_DIR = str(Path(__file__).resolve().parents[1])
OPENWEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"


def _load_weather_server(api_key: str = "test-key"):
    if MCP_SERVERS_DIR not in sys.path:
        sys.path.insert(0, MCP_SERVERS_DIR)
    os.environ["OPENWEATHER_API_KEY"] = api_key
    if "weather_server" in sys.modules:
        return importlib.reload(sys.modules["weather_server"])
    import weather_server  # noqa: PLC0415

    return weather_server


def _weather_payload(city: str = "Beijing") -> dict:
    return {
        "name": city,
        "sys": {"country": "CN"},
        "main": {"temp": 22.5, "humidity": 40},
        "wind": {"speed": 3.1},
        "weather": [{"description": "晴"}],
    }


@pytest.mark.asyncio
async def test_missing_api_key_short_circuits_without_http_call():
    ws = _load_weather_server(api_key="")
    with respx.mock:
        result = await ws.fetch_weather("NoKeyCity")
    assert result["ok"] is False
    assert result["error"]["code"] == "provider"
    assert "OPENWEATHER_API_KEY" in result["error"]["message"]


@pytest.mark.asyncio
async def test_successful_query_is_cached_on_second_call():
    ws = _load_weather_server()
    with respx.mock:
        route = respx.get(OPENWEATHER_URL).mock(
            return_value=httpx.Response(200, json=_weather_payload("CacheCity"))
        )

        first = await ws.fetch_weather("CacheCity")
        assert first["ok"] is True
        assert first.get("from_cache") is not True

        second = await ws.fetch_weather("CacheCity")
        assert second["ok"] is True
        assert second["from_cache"] is True

        assert route.call_count == 1  # 第二次没有真的再打一次 HTTP


@pytest.mark.asyncio
async def test_5xx_is_retried_then_succeeds():
    ws = _load_weather_server()
    with respx.mock:
        route = respx.get(OPENWEATHER_URL).mock(
            side_effect=[
                httpx.Response(500, text="server error"),
                httpx.Response(200, json=_weather_payload("RetryCity")),
            ]
        )

        result = await ws.fetch_weather("RetryCity")

        assert result["ok"] is True
        assert route.call_count == 2


@pytest.mark.asyncio
async def test_persistent_5xx_exhausts_retries_and_reports_provider_error():
    ws = _load_weather_server()
    with respx.mock:
        route = respx.get(OPENWEATHER_URL).mock(return_value=httpx.Response(503, text="down"))

        result = await ws.fetch_weather("AlwaysDownCity")

        assert result["ok"] is False
        assert result["error"]["code"] == "provider"
        assert result["error"]["retryable"] is True
        assert route.call_count == ws.MAX_ATTEMPTS


@pytest.mark.asyncio
async def test_4xx_is_not_retried():
    ws = _load_weather_server()
    with respx.mock:
        route = respx.get(OPENWEATHER_URL).mock(return_value=httpx.Response(404, text="city not found"))

        result = await ws.fetch_weather("UnknownCity")

        assert result["ok"] is False
        assert result["error"]["code"] == "validation"
        assert result["error"]["retryable"] is False
        assert route.call_count == 1  # 4xx 是调用方参数问题，重试没有意义，不该重试


@pytest.mark.asyncio
async def test_timeout_is_retried():
    ws = _load_weather_server()
    with respx.mock:
        route = respx.get(OPENWEATHER_URL).mock(
            side_effect=[
                httpx.TimeoutException("timed out"),
                httpx.Response(200, json=_weather_payload("TimeoutCity")),
            ]
        )

        result = await ws.fetch_weather("TimeoutCity")

        assert result["ok"] is True
        assert route.call_count == 2


@pytest.mark.asyncio
async def test_query_weather_tool_includes_human_readable_summary():
    ws = _load_weather_server()
    with respx.mock:
        respx.get(OPENWEATHER_URL).mock(return_value=httpx.Response(200, json=_weather_payload("SummaryCity")))

        result = await ws.query_weather("SummaryCity")

        assert result["ok"] is True
        assert "SummaryCity" in result["summary"]
        assert "晴" in result["summary"]
