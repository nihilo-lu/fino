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
    # 收入、支出、权益、资产 类账户不需要设置币种，默认 CNY
    currency = data.get("currency") or "CNY"
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
        err_msg = str(e)
        if "UNIQUE constraint" in err_msg or "unique constraint" in err_msg or "duplicate key" in err_msg.lower():
            if "ledger_id" in err_msg and "name" in err_msg:
                return api_error("该账本下已存在同名账户，请使用其他名称", 400)
        logger.error(f"Create account error: {e}", exc_info=True)
        return api_error(err_msg, 500)


@accounts_bp.route("/accounts/<int:account_id>", methods=["PUT"])
def update_account(account_id):
    data = request.get_json() or {}
    name = data.get("name")
    acc_type = data.get("type")
    currency = data.get("currency")  # 可选，前端不传则保持原币种
    description = data.get("description", "")

    if not all([name, acc_type]):
        return api_error("账户名称和类型为必填", 400)

    try:
        database = get_db()
        ok = database.update_account(account_id, name, acc_type, currency, description)
        if ok:
            return api_success(message="账户更新成功")
        # update_account 返回 False：账户不存在、同名冲突或币种无效等
        return api_error("更新失败，账户不存在、同名冲突或币种无效", 400)
    except Exception as e:
        logger.error(f"Update account error: {e}", exc_info=True)
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


@accounts_bp.route("/accounts/balances", methods=["GET"])
def get_account_balances():
    """获取账本下各账户的资金余额（现金余额：本金投入-撤出+收入-支出+内转-开仓+平仓）"""
    ledger_id = request.args.get("ledger_id", type=int)
    if ledger_id is None:
        return api_error("需要 ledger_id 参数", 400)
    try:
        database = get_db()
        accounts = database.get_accounts(ledger_id)
        if accounts.empty:
            return api_success(data={"balances": []})
        balances = []
        for _, row in accounts.iterrows():
            acc_id = int(row["id"])
            bal = database.get_account_balance(acc_id)
            cash_by_currency = database.get_account_cash_balance_by_currency(acc_id)
            balances.append({
                "account_id": acc_id,
                "account_name": row.get("name", ""),
                "account_type": row.get("type", ""),
                "currency": row.get("currency", "CNY"),
                "balance": float(bal.get("balance", 0)),
                "cash_balances": cash_by_currency,
                "total_invest": float(bal.get("total_invest", 0)),
                "total_withdraw": float(bal.get("total_withdraw", 0)),
                "total_income": float(bal.get("total_income", 0)),
                "total_expense": float(bal.get("total_expense", 0)),
                "transfer_in": float(bal.get("transfer_in", 0)),
                "transfer_out": float(bal.get("transfer_out", 0)),
                "total_open": float(bal.get("total_open", 0)),
                "total_close": float(bal.get("total_close", 0)),
            })
        return api_success(data={"balances": balances})
    except Exception as e:
        logger.error(f"Get account balances error: {e}", exc_info=True)
        return api_error(str(e), 500)
