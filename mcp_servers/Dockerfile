# 只给 map_server（Streamable HTTP，独立服务）用；weather/write 是 backend 的
# stdio 子进程，跟着 backend 镜像走，不需要自己的容器。
FROM python:3.11-slim

WORKDIR /app

# mcp 2.x 把 FastMCP 改名成 MCPServer，是破坏性变更；backend 那边靠
# langchain-mcp-adapters 间接把 mcp 锁在 1.x，这里必须显式锁一样的范围，
# 不然两个镜像装到不同大版本——这个坑是真的在构建这个镜像时踩到的。
RUN pip install --no-cache-dir "mcp<2" httpx python-dotenv

COPY mcp_servers/common.py mcp_servers/map_server.py ./

EXPOSE 8811

CMD ["python", "map_server.py"]
