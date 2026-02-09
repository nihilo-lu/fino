"""
账户蓝图 - 账户 CRUD
"""

import logging
from flask import Blueprint, request

from app.extensions import get_db
from app.utils import cors_jsonify

logger = logging.getLogger(__name__)

accounts_bp = Blueprint("accounts", __name__, url_prefix="/api")


@accounts_bp.route("/accounts", methods=["GET"])
def get_accounts():
    ledger_id = request.args.get("ledger_id", type=int)
    try:
        database = get_db()
        accounts = database.get_accounts(ledger_id)
        accounts_list = accounts.to_dict(orient="records") if not accounts.empty else []
        return cors_jsonify({"accounts": accounts_list})
    except Exception as e:
        logger.error(f"Get accounts error: {e}")
        return cors_jsonify({"error": str(e)}, 500)


@accounts_bp.route("/accounts", methods=["POST"])
def create_account():
    data = request.get_json()
    ledger_id = data.get("ledger_id")
    name = data.get("name")
    acc_type = data.get("type")
    currency = data.get("currency", "CNY")
    description = data.get("description", "")

    if not all([ledger_id, name, acc_type]):
        return cors_jsonify({"error": "账本ID、账户名称和类型为必填"}, 400)

    try:
        database = get_db()
        result = database.add_account(ledger_id, name, acc_type, currency, description)
        if result:
            return cors_jsonify({"success": True, "message": "账户创建成功"})
        return cors_jsonify({"error": "创建账户失败"}, 500)
    except Exception as e:
        logger.error(f"Create account error: {e}")
        return cors_jsonify({"error": str(e)}, 500)
