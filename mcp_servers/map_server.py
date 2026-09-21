"""Map MCP Server。

用 OpenStreetMap 的 Nominatim 公共 API 实现一个真正能跑、不需要 Key 的
地理编码 / 逆地理编码 Server，通过 Streamable HTTP 暴露。README 里写了
怎么换成高德官方 MCP（需要用户自己申请 Key）。

Nominatim 的使用政策要求：合理的 User-Agent、不超过约 1 请求/秒，这里用一个
模块级的节流锁保证这一点。
"""

from __future__ import annotations

import asyncio
import os
import time

import httpx
from mcp.server.fastmcp import FastMCP

from common import err, ok

MIN_INTERVAL_S = 1.1  # 略大于 Nominatim 要求的 1 req/s，留点余量
NOMINATIM_BASE = "https://nominatim.openstreetmap.org"
USER_AGENT = "mcp-multi-tool-agent-map/1.0"
REQUEST_TIMEOUT_S = 10.0

_rate_lock = asyncio.Lock()
_last_request_at = 0.0

mcp = FastMCP(
    "MapServer",
    host=os.getenv("MAP_SERVER_HOST", "0.0.0.0"),
    port=int(os.getenv("MAP_SERVER_PORT", "8811")),
)


async def _throttled_get(path: str, params: dict) -> httpx.Response:
    global _last_request_at
    async with _rate_lock:
        wait = MIN_INTERVAL_S - (time.monotonic() - _last_request_at)
        if wait > 0:
            await asyncio.sleep(wait)
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_S) as client:
            response = await client.get(
                f"{NOMINATIM_BASE}{path}",
                params=params,
                headers={"User-Agent": USER_AGENT},
            )
        _last_request_at = time.monotonic()
        return response


@mcp.tool()
async def geocode(query: str, limit: int = 3) -> dict:
    """
    地点搜索（地理编码）：把地名/地址转换成经纬度。
    :param query: 地名或地址，比如 "天安门" 或 "Eiffel Tower"。
    :param limit: 最多返回几个候选结果，默认 3。
    """
    try:
        response = await _throttled_get(
            "/search", {"q": query, "format": "jsonv2", "limit": limit}
        )
    except httpx.TimeoutException:
        return err("timeout", f"请求超过 {REQUEST_TIMEOUT_S}s", retryable=True)
    except httpx.RequestError as exc:
        return err("transport", f"网络请求失败: {exc}", retryable=True)

    if response.status_code >= 500:
        return err("provider", f"Nominatim 服务端错误: {response.status_code}", retryable=True)
    if response.status_code >= 400:
        return err("validation", f"Nominatim 请求错误: {response.status_code}", retryable=False)

    results = response.json()
    if not results:
        return err("validation", f"未找到匹配地点: {query}", retryable=False)

    return ok(
        [
            {
                "display_name": item.get("display_name"),
                "lat": item.get("lat"),
                "lon": item.get("lon"),
                "type": item.get("type"),
            }
            for item in results
        ]
    )


@mcp.tool()
async def reverse_geocode(lat: float, lon: float) -> dict:
    """
    逆地理编码：把经纬度转换成地址描述。
    :param lat: 纬度
    :param lon: 经度
    """
    try:
        response = await _throttled_get(
            "/reverse", {"lat": lat, "lon": lon, "format": "jsonv2"}
        )
    except httpx.TimeoutException:
        return err("timeout", f"请求超过 {REQUEST_TIMEOUT_S}s", retryable=True)
    except httpx.RequestError as exc:
        return err("transport", f"网络请求失败: {exc}", retryable=True)

    if response.status_code >= 500:
        return err("provider", f"Nominatim 服务端错误: {response.status_code}", retryable=True)
    if response.status_code >= 400:
        return err("validation", f"Nominatim 请求错误: {response.status_code}", retryable=False)

    data = response.json()
    if "error" in data:
        return err("validation", str(data["error"]), retryable=False)

    return ok({"display_name": data.get("display_name"), "address": data.get("address")})


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
