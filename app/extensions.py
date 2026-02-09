"""
应用扩展模块 - 延迟初始化的扩展
数据库等资源在首次使用时初始化，避免循环导入
"""

from flask import g, current_app


def get_db():
    """获取数据库实例（按应用实例缓存）"""
    if "database" not in current_app.extensions:
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        from database import Database
        config_path = current_app.config.get("CONFIG_PATH")
        current_app.extensions["database"] = Database(config_path=config_path)
    return current_app.extensions["database"]
