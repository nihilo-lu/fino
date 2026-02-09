"""
资金明细蓝图 - 资金流水 CRUD
"""

import logging
from flask import Blueprint, request

from app.extensions import get_db
from app.utils import cors_jsonify

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

        return cors_jsonify({
            "fund_transactions": fund_list,
            "limit": limit,
            "offset": offset,
        })
    except Exception as e:
        logger.error(f"Get fund transactions error: {e}")
        return cors_jsonify({"error": str(e)}, 500)


@fund_transactions_bp.route("/fund-transactions", methods=["POST"])
def create_fund_transaction():
    data = request.get_json()

    required_fields = ["ledger_id", "account_id", "type", "date"]
    if not all(data.get(f) for f in required_fields):
        return cors_jsonify({"error": "缺少必填字段"}, 400)

    try:
        database = get_db()
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

        result = database.add_fund_transaction(fund_trans)
        if result:
            return cors_jsonify({"success": True, "message": "资金明细添加成功"})
        return cors_jsonify({"error": "添加资金明细失败"}, 500)
    except Exception as e:
        logger.error(f"Create fund transaction error: {e}")
        return cors_jsonify({"error": str(e)}, 500)
