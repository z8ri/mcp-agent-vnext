"""Weather MCP Server。

- 网络类失败（超时、5xx、连接错误）自动重试 2 次，4xx（比如城市名拼错）不重试；
- 同一个城市 5 分钟内的重复查询走内存缓存，不重复打 OpenWeather；
- 出错时返回结构化 {ok, error{code,message,retryable}}，不是裸字符串糊给模型。
"""

from __future__ import annotations

import os

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from common import TTLCache, err, ok

load_dotenv()

mcp = FastMCP("WeatherServer")

OPENWEATHER_API_BASE = "https://api.openweathermap.org/data/2.5/weather"
API_KEY = os.getenv("OPENWEATHER_API_KEY", "")
USER_AGENT = "mcp-multi-tool-agent-weather/1.0"
REQUEST_TIMEOUT_S = 30.0
MAX_ATTEMPTS = 3

_cache = TTLCache(ttl_seconds=300)


async def _fetch_weather_once(city: str) -> httpx.Response:
    params = {"q": city, "appid": API_KEY, "units": "metric", "lang": "zh_cn"}
    headers = {"User-Agent": USER_AGENT}
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_S) as client:
        return await client.get(OPENWEATHER_API_BASE, params=params, headers=headers)


async def fetch_weather(city: str) -> dict:
    if not API_KEY:
        return err("provider", "未配置 OPENWEATHER_API_KEY", retryable=False)

    cached = _cache.get(city)
    if cached is not None:
        cached_copy = dict(cached)
        cached_copy["from_cache"] = True
        return cached_copy

    last_error: dict | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = await _fetch_weather_once(city)
        except httpx.TimeoutException:
            last_error = err("timeout", f"请求超过 {REQUEST_TIMEOUT_S}s", retryable=True)
            continue
        except httpx.RequestError as exc:
            last_error = err("transport", f"网络请求失败: {exc}", retryable=True)
            continue

        if response.status_code >= 500:
            last_error = err("provider", f"OpenWeather 服务端错误: {response.status_code}", retryable=True)
            continue
        if response.status_code >= 400:
            # 4xx 是调用方参数问题（比如城市名不存在），重试没有意义。
            return err("validation", f"OpenWeather 请求错误: {response.status_code} {response.text[:200]}", retryable=False)

        result = ok(response.json())
        _cache.set(city, result)
        return result

    assert last_error is not None
    return last_error


def format_weather(payload: dict) -> str:
    if not payload.get("ok"):
        return f"⚠️ {payload['error']['message']}"

    data = payload["data"]
    city = data.get("name", "未知")
    country = data.get("sys", {}).get("country", "未知")
    temp = data.get("main", {}).get("temp", "N/A")
    humidity = data.get("main", {}).get("humidity", "N/A")
    wind_speed = data.get("wind", {}).get("speed", "N/A")
    description = data.get("weather", [{}])[0].get("description", "未知")

    return (
        f"🌍 {city}, {country}\n"
        f"🌡 温度: {temp}°C\n"
        f"💧 湿度: {humidity}%\n"
        f"🌬 风速: {wind_speed} m/s\n"
        f"🌤 天气: {description}\n"
    )


@mcp.tool()
async def query_weather(city: str) -> dict:
    """
    输入指定城市的英文名称，返回今日天气查询结果。
    :param city: 城市名称（需使用英文，如 Beijing）
    :return: {"ok": true, "data": {...}} 或 {"ok": false, "error": {...}}；
             另外附带一段人类可读的 "summary" 文本方便模型直接引用。
    """
    payload = await fetch_weather(city)
    payload["summary"] = format_weather(payload)
    return payload


@mcp.tool()
async def get_weather_tips(season: str) -> dict:
    """
    获取指定季节的天气贴士。
    这是演示同一个 MCP Server 可以包含多个 Tool 的例子。
    :param season: 季节名称 (spring, summer, autumn, winter)
    """
    tips = {
        "spring": "🌸 春季多风，注意防风保暖，预防花粉过敏。",
        "summer": "☀️ 夏季炎热，注意防暑降温，多喝水。",
        "autumn": "🍁 秋季干燥，注意补水润肺，早晚温差大。",
        "winter": "❄️ 冬季寒冷，注意防寒保暖，预防感冒。",
    }
    tip = tips.get(season.lower())
    if tip is None:
        return err("validation", f"未知季节: {season}", retryable=False)
    return ok(tip)


if __name__ == "__main__":
    mcp.run(transport="stdio")
