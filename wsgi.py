"""
WSGI 入口（用于 Gunicorn / uWSGI 等生产服务器）

注意：
- 本仓库同时存在 `app/` 包与根目录 `app.py` 文件，直接使用 `app:app` 容易发生导入歧义。
- 因此建议生产环境统一使用 `wsgi:app` 作为入口。
"""

from app import create_app
from app.config import get_config_path

app = create_app(config_path=get_config_path())

