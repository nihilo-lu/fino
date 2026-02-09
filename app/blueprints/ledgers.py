"""
账本蓝图 - 账本 CRUD
"""

import logging
from flask import Blueprint, request

from app.extensions import get_db
from app.utils import cors_jsonify

logger = logging.getLogger(__name__)

ledgers_bp = Blueprint("ledgers", __name__, url_prefix="/api")


@ledgers_bp.route("/ledgers", methods=["GET"])
def get_ledgers():
    username = request.args.get("username")
    if not username:
        return cors_jsonify({"error": "需要用户名参数"}, 400)
    try:
        database = get_db()
        ledgers = database.get_ledgers(username)
        ledgers_list = ledgers.to_dict(orient="records") if not ledgers.empty else []
        return cors_jsonify({"ledgers": ledgers_list})
    except Exception as e:
        logger.error(f"Get ledgers error: {e}")
        return cors_jsonify({"error": str(e)}, 500)


@ledgers_bp.route("/ledgers", methods=["POST"])
def create_ledger():
    data = request.get_json()
    username = data.get("username")
    name = data.get("name")
    description = data.get("description", "")
    cost_method = data.get("cost_method", "FIFO")

    if not all([username, name]):
        return cors_jsonify({"error": "用户名和账本名称为必填"}, 400)

    try:
        database = get_db()
        result = database.add_ledger(name, description, cost_method, username)
        if result:
            return cors_jsonify({"success": True, "message": "账本创建成功"})
        return cors_jsonify({"error": "创建账本失败"}, 500)
    except Exception as e:
        logger.error(f"Create ledger error: {e}")
        return cors_jsonify({"error": str(e)}, 500)
