"""
投资追踪器 API 服务器 - 入口文件

提供 REST API 接口，供前端调用后端业务逻辑

启动方式:
    python app.py

默认端口: 8087
"""

import os
import sys

# 确保项目根目录在 Python 路径中
sys.path.insert(0, os.path.dirname(__file__))

from app import create_app
from app.config import get_config_path

PORT = 8087
URL = f"http://localhost:{PORT}"


def _print_startup_banner():
    """Docker 风格就绪横幅：多分隔符 + 项目名 + 访问地址"""
    w = 58
    sep = "=" * 62
    star = "*" * 62
    blank = "*" + " " * w + "*"
    print()
    print(sep)
    print(star)
    print(blank)
    print("*" + "   F I N O  ·  投 资 追 踪 器".ljust(w) + "*")
    print(blank)
    print("*" + "   服 务 已 就 绪".ljust(w) + "*")
    print(blank)
    print("*" + f"   {URL}".ljust(w) + "*")
    print(blank)
    print(star)
    print(sep)
    print()


if __name__ == "__main__":
    # 仅在主进程输出，避免 debug 重载时重复打印
    verbose = os.environ.get("WERKZEUG_RUN_MAIN") != "true"

    if verbose:
        print("\n[1/2] 正在加载配置与插件 …")

    app = create_app(config_path=get_config_path())

    if verbose:
        print("      ✓ 配置与插件就绪")

    if verbose:
        print("[2/2] 正在初始化数据库 …")

    with app.app_context():
        from app.extensions import get_db
        get_db()

    if verbose:
        print("      ✓ 数据库就绪")
        _print_startup_banner()

    app.run(host="0.0.0.0", port=PORT, debug=True)
