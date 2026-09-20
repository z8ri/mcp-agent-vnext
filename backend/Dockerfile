# 构建上下文必须是仓库根目录（不是 backend/），因为 weather/write MCP Server
# 是 backend 用 stdio 子进程的方式启动的（server_specs.py 里 `sys.executable` +
# 相对路径去找 mcp_servers/*.py），两边要保持和本地开发一样的相对目录结构，
# 不能只把 backend/ 单独打进镜像。
FROM python:3.11-slim

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend backend
COPY mcp_servers mcp_servers

WORKDIR /app/backend
ENV PYTHONPATH=/app/backend

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
