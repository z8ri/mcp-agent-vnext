# 构建上下文是仓库根目录（跟 backend/Dockerfile 保持一致的约定）。
FROM node:20-slim AS build
WORKDIR /app

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend .

# 前端在构建时（不是运行时）把 API 地址编译进产物里——Vite 是这么处理 env 的，
# 不是运行时能改的配置；换后端地址需要重新 build 这个镜像。
ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
