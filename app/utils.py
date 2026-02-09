"""
应用级工具函数 - 统一响应格式、JSON 序列化
"""

from datetime import datetime, date
from flask import jsonify


def json_default(obj):
    """JSON 序列化默认处理器"""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def cors_jsonify(data, status=200):
    """返回带状态码的 JSON 响应（兼容旧用法）"""
    response = jsonify(data)
    response.status_code = status
    return response


# ============ 统一 API 响应格式 ============
# 成功: { success: true, data?: any, message?: string }
# 失败: { success: false, error: string }


def api_success(data=None, message: str | None = None, status=200):
    """统一成功响应。data 为 dict 时合并到顶层，便于前端直接使用 data.ledgers 等"""
    body = {"success": True}
    if data is not None:
        if isinstance(data, dict):
            body.update(data)
        else:
            body["data"] = data
    if message:
        body["message"] = message
    response = jsonify(body)
    response.status_code = status
    return response


def api_error(error: str, status=400):
    """统一错误响应"""
    response = jsonify({"success": False, "error": error})
    response.status_code = status
    return response
