"""
应用级工具函数
"""

from datetime import datetime, date
from flask import jsonify


def json_default(obj):
    """JSON 序列化默认处理器"""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def cors_jsonify(data, status=200):
    """返回带状态码的 JSON 响应"""
    response = jsonify(data)
    response.status_code = status
    return response
