FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 依赖
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt \
    && pip install --no-cache-dir gunicorn

# 代码
COPY . /app

EXPOSE 8087

# 默认使用 Gunicorn 跑 API（入口见 wsgi.py）
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:8087", "wsgi:app"]

