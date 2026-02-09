"""
账户蓝图 - 账户 CRUD
"""

import logging
from flask import Blueprint, request

from app.extensions import get_db
from app.utils import api_error, api_success

logger = logging.getLogger(__name__)

accounts_bp = Blueprint("accounts", __name__, url_prefix="/api")


@accounts_bp.route("/accounts", methods=["GET"])
def get_accounts():
    ledger_id = request.args.get("ledger_id", type=int)
    if ledger_id is None:
        return api_error("需要 ledger_id 参数", 400)
    try:
        database = get_db()
        accounts = database.get_accounts(ledger_id)
        accounts_list = accounts.to_dict(orient="records") if not accounts.empty else []
        return api_success(data={"accounts": accounts_list})
    except Exception as e:
        logger.error(f"Get accounts error: {e}", exc_info=True)
        return api_error(str(e), 500)


@accounts_bp.route("/accounts", methods=["POST"])
def create_account():
    data = request.get_json()
    ledger_id = data.get("ledger_id")
    name = data.get("name")
    acc_type = data.get("type")
    currency = data.get("currency", "CNY")
    description = data.get("description", "")

    if not all([ledger_id, name, acc_type]):
        return api_error("账本ID、账户名称和类型为必填", 400)

    try:
        database = get_db()
        result = database.add_account(ledger_id, name, acc_type, currency, description)
        if result:
            return api_success(message="账户创建成功")
        return api_error("创建账户失败，请检查币种是否存在（如 CNY）", 500)
    except Exception as e:
        logger.error(f"Create account error: {e}", exc_info=True)
        return api_error(str(e), 500)


@accounts_bp.route("/accounts/<int:account_id>", methods=["DELETE"])
def delete_account(account_id):
    try:
        database = get_db()
        result = database.delete_account(account_id)
        if result:
            return api_success(message="账户删除成功")
        return api_error("删除失败，账户不存在或有关联数据", 404)
    except Exception as e:
        logger.error(f"Delete account error: {e}")
        return api_error(str(e), 500)
