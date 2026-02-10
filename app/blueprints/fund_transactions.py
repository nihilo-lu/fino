"""
资金明细蓝图 - 资金流水 CRUD
"""

import logging
from flask import Blueprint, request

from app.extensions import get_db
from app.utils import api_error, api_success

logger = logging.getLogger(__name__)

fund_transactions_bp = Blueprint("fund_transactions", __name__, url_prefix="/api")


@fund_transactions_bp.route("/fund-transactions", methods=["GET"])
def get_fund_transactions():
    ledger_id = request.args.get("ledger_id", type=int)
    account_id = request.args.get("account_id", type=int)
    trans_type = request.args.get("type")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    limit = request.args.get("limit", type=int, default=50)
    offset = request.args.get("offset", type=int, default=0)

    try:
        database = get_db()
        fund_transactions = database.get_fund_transactions(
            ledger_id=ledger_id,
            account_id=account_id,
            trans_type=trans_type,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset,
        )
        fund_list = fund_transactions.to_dict(orient="records") if not fund_transactions.empty else []

        return api_success(data={
            "fund_transactions": fund_list,
            "limit": limit,
            "offset": offset,
        })
    except Exception as e:
        logger.error(f"Get fund transactions error: {e}")
        return api_error(str(e), 500)


@fund_transactions_bp.route("/fund-transactions", methods=["POST"])
def create_fund_transaction():
    data = request.get_json() or {}

    # 支持多借多贷：传入 entries 时按借贷记账法校验
    entries = data.get("entries")
    if entries and isinstance(entries, list) and len(entries) > 0:
        required = ["ledger_id", "type", "date"]
        if not all(data.get(f) for f in required):
            return api_error("使用分录时缺少必填字段：ledger_id, type, date", 400)
        for i, e in enumerate(entries):
            if not e.get("account_id") or e.get("side") not in ("debit", "credit"):
                return api_error(f"分录第 {i + 1} 行缺少 account_id 或无效的 side（须为 debit/credit）", 400)
            try:
                e["amount"] = float(e.get("amount", 0))
            except (TypeError, ValueError):
                return api_error(f"分录第 {i + 1} 行金额无效", 400)
        fund_trans = {
            "ledger_id": data["ledger_id"],
            "date": data["date"],
            "type": data["type"],
            "currency": data.get("currency", "CNY"),
            "notes": data.get("notes", data.get("description", "") or ""),
            "entries": [
                {
                    "account_id": int(e["account_id"]),
                    "side": e["side"],
                    "amount": float(e["amount"]),
                    "currency": e.get("currency", data.get("currency", "CNY")),
                    "subject_type": e.get("subject_type", "cash"),
                }
                for e in entries
            ],
        }
    else:
        # 兼容旧格式：单笔金额 + 单账户
        required_fields = ["ledger_id", "account_id", "type", "date"]
        if not all(data.get(f) for f in required_fields):
            return api_error("缺少必填字段", 400)
        fund_trans = {
            "ledger_id": data.get("ledger_id"),
            "account_id": data.get("account_id"),
            "type": data.get("type"),
            "date": data.get("date"),
            "amount": data.get("amount"),
            "currency": data.get("currency", "CNY"),
            "exchange_rate": data.get("exchange_rate", 1.0),
            "amount_cny": data.get("amount_cny"),
            "description": data.get("description", ""),
        }

    try:
        database = get_db()
        result = database.add_fund_transaction(fund_trans)
        if result:
            return api_success(message="资金明细添加成功")
        return api_error("添加资金明细失败", 500)
    except ValueError as e:
        return api_error(str(e), 400)
    except Exception as e:
        logger.error(f"Create fund transaction error: {e}")
        return api_error(str(e), 500)


@fund_transactions_bp.route("/fund-transactions/<int:fund_id>", methods=["GET"])
def get_fund_transaction(fund_id):
    try:
        database = get_db()
        fund = database.get_fund_transaction_by_id(fund_id)
        if not fund:
            return api_error("资金明细不存在", 404)
        return api_success(data=fund)
    except Exception as e:
        logger.error(f"Get fund transaction error: {e}")
        return api_error(str(e), 500)


@fund_transactions_bp.route("/fund-transactions/<int:fund_id>", methods=["PUT"])
def update_fund_transaction(fund_id):
    data = request.get_json() or {}
    entries = data.get("entries")
    if not entries or not isinstance(entries, list) or len(entries) == 0:
        return api_error("请提供 entries 数组", 400)
    required = ["ledger_id", "type", "date"]
    if not all(data.get(f) for f in required):
        return api_error("缺少必填字段：ledger_id, type, date", 400)
    for i, e in enumerate(entries):
        if not e.get("account_id") or e.get("side") not in ("debit", "credit"):
            return api_error(f"分录第 {i + 1} 行缺少 account_id 或无效的 side", 400)
        try:
            e["amount"] = float(e.get("amount", 0))
        except (TypeError, ValueError):
            return api_error(f"分录第 {i + 1} 行金额无效", 400)
    fund_trans = {
        "ledger_id": data["ledger_id"],
        "date": data["date"],
        "type": data["type"],
        "currency": data.get("currency", "CNY"),
        "notes": data.get("notes", ""),
        "entries": [
            {
                "account_id": int(e["account_id"]),
                "side": e["side"],
                "amount": float(e["amount"]),
                "currency": e.get("currency", data.get("currency", "CNY")),
                "subject_type": e.get("subject_type", "cash"),
            }
            for e in entries
        ],
    }
    try:
        database = get_db()
        result = database.update_fund_transaction(fund_id, fund_trans)
        if result:
            return api_success(message="更新成功")
        return api_error("更新失败", 500)
    except ValueError as e:
        return api_error(str(e), 400)
    except Exception as e:
        logger.error(f"Update fund transaction error: {e}")
        return api_error(str(e), 500)


@fund_transactions_bp.route("/fund-transactions/<int:fund_id>", methods=["DELETE"])
def delete_fund_transaction(fund_id):
    try:
        database = get_db()
        result = database.delete_fund_transaction(fund_id)
        if result:
            return api_success(message="删除成功")
        return api_error("删除失败", 404)
    except Exception as e:
        logger.error(f"Delete fund transaction error: {e}")
        return api_error(str(e), 500)


@fund_transactions_bp.route("/fund-transactions/batch-delete", methods=["POST"])
def batch_delete_fund_transactions():
    data = request.get_json() or {}
    ids = data.get("ids", [])
    if not ids or not isinstance(ids, list):
        return api_error("请提供 ids 数组", 400)
    try:
        database = get_db()
        for fid in ids:
            database.delete_fund_transaction(int(fid))
        return api_success(message="删除成功")
    except Exception as e:
        logger.error(f"Batch delete fund transactions error: {e}")
        return api_error(str(e), 500)
