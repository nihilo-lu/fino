"""
参考数据蓝图 - 分类、币种
"""

import logging
from flask import Blueprint, request

from app.extensions import get_db
from app.utils import api_error, api_success

logger = logging.getLogger(__name__)

reference_bp = Blueprint("reference", __name__, url_prefix="/api")


@reference_bp.route("/categories", methods=["GET"])
def get_categories():
    try:
        database = get_db()
        categories = database.get_categories()
        categories_list = categories.to_dict(orient="records") if not categories.empty else []
        return api_success(data={"categories": categories_list})
    except Exception as e:
        logger.error(f"Get categories error: {e}")
        return api_error(str(e), 500)


@reference_bp.route("/categories", methods=["POST"])
def create_category():
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    description = (data.get("description") or "").strip()

    if not name:
        return api_error("类别名称为必填", 400)

    try:
        database = get_db()
        result = database.add_category(name, description or None)
        if result:
            return api_success(message="类别创建成功")
        return api_error("类别名称已存在", 400)
    except Exception as e:
        logger.error(f"Create category error: {e}")
        return api_error(str(e), 500)


@reference_bp.route("/categories/<int:category_id>", methods=["PUT"])
def update_category(category_id):
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    description = (data.get("description") or "").strip()

    if not name:
        return api_error("类别名称为必填", 400)

    try:
        database = get_db()
        result = database.update_category(category_id, name, description or None)
        if result:
            return api_success(message="类别更新成功")
        return api_error("更新失败，类别不存在或名称已存在", 404)
    except Exception as e:
        logger.error(f"Update category error: {e}")
        return api_error(str(e), 500)


@reference_bp.route("/categories/<int:category_id>", methods=["DELETE"])
def delete_category(category_id):
    try:
        database = get_db()
        result = database.delete_category(category_id)
        if result:
            return api_success(message="类别删除成功")
        return api_error("删除失败，类别不存在或已被交易/持仓使用", 400)
    except Exception as e:
        logger.error(f"Delete category error: {e}")
        return api_error(str(e), 500)


@reference_bp.route("/currencies", methods=["GET"])
def get_currencies():
    try:
        database = get_db()
        currencies = database.get_currencies()
        currencies_list = currencies.to_dict(orient="records") if not currencies.empty else []
        return api_success(data={"currencies": currencies_list})
    except Exception as e:
        logger.error(f"Get currencies error: {e}")
        return api_error(str(e), 500)
