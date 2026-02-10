FROM nginx:1.27-alpine

# Nginx 配置
COPY deploy/nginx/nginx.conf /etc/nginx/conf.d/default.conf

# 前端资源（保持现有路径约定：/frontend/*）
COPY frontend /usr/share/nginx/html/frontend

# 根路径需要 index.html / manifest.json / sw.js
COPY frontend/index.html /usr/share/nginx/html/index.html
COPY frontend/manifest.json /usr/share/nginx/html/manifest.json
COPY frontend/sw.js /usr/share/nginx/html/sw.js

