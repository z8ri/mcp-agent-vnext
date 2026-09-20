# 只给 map_server（Streamable HTTP，独立服务）用；weather/write 是 backend 的
# stdio 子进程，跟着 backend 镜像走，不需要自己的容器。
FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir mcp httpx python-dotenv

COPY mcp_servers/common.py mcp_servers/map_server.py ./

EXPOSE 8811

CMD ["python", "map_server.py"]
