"""
投资追踪器 API 服务器 - 入口文件

提供 REST API 接口，供前端调用后端业务逻辑

启动方式:
    python app.py

默认端口: 8085
"""

import os
import sys

# 确保项目根目录在 Python 路径中
sys.path.insert(0, os.path.dirname(__file__))

from app import create_app
from app.config import get_config_path

app = create_app(config_path=get_config_path())

if __name__ == "__main__":
    print("=" * 60)
    print("  投资追踪器 API 服务器")
    print("  地址: http://localhost:8085")
    print("=" * 60)
    app.run(host="0.0.0.0", port=8086, debug=True)
