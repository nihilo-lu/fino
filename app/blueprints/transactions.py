"""
交易蓝图 - 交易记录 CRUD
"""

import logging
from flask import Blueprint, request

from app.extensions import get_db
from app.utils import cors_jsonify

logger = logging.getLogger(__name__)

transactions_bp = Blueprint("transactions", __name__, url_prefix="/api")


@transactions_bp.route("/transactions", methods=["GET"])
def get_transactions():
    ledger_id = request.args.get("ledger_id", type=int)
    account_id = request.args.get("account_id", type=int)
    trans_type = request.args.get("type")
    category = request.args.get("category")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    limit = request.args.get("limit", type=int, default=50)
    offset = request.args.get("offset", type=int, default=0)

    try:
        database = get_db()
        transactions = database.get_transactions(
            ledger_id=ledger_id,
            account_id=account_id,
            trans_type=trans_type,
            category=category,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset,
        )
        transactions_list = transactions.to_dict(orient="records") if not transactions.empty else []

        total_count = database.get_transactions_count(
            ledger_id=ledger_id,
            account_id=account_id,
            trans_type=trans_type,
            category=category,
            start_date=start_date,
            end_date=end_date,
        )

        return cors_jsonify({
            "transactions": transactions_list,
            "total": total_count,
            "limit": limit,
            "offset": offset,
        })
    except Exception as e:
        logger.error(f"Get transactions error: {e}")
        return cors_jsonify({"error": str(e)}, 500)


@transactions_bp.route("/transactions", methods=["POST"])
def create_transaction():
    data = request.get_json()

    required_fields = ["ledger_id", "account_id", "type", "code", "name", "date"]
    if not all(data.get(f) for f in required_fields):
        return cors_jsonify({"error": "缺少必填字段"}, 400)

    try:
        database = get_db()
        transaction = {
            "ledger_id": data.get("ledger_id"),
            "account_id": data.get("account_id"),
            "type": data.get("type"),
            "code": data.get("code"),
            "name": data.get("name"),
            "date": data.get("date"),
            "price": data.get("price"),
            "quantity": data.get("quantity"),
            "amount": data.get("amount"),
            "fee": data.get("fee", 0),
            "category": data.get("category"),
            "notes": data.get("notes", ""),
        }

        result = database.add_transaction(transaction)
        if result:
            return cors_jsonify({"success": True, "message": "交易记录添加成功"})
        return cors_jsonify({"error": "添加交易记录失败"}, 500)
    except Exception as e:
        logger.error(f"Create transaction error: {e}")
        return cors_jsonify({"error": str(e)}, 500)


@transactions_bp.route("/transactions/<int:transaction_id>", methods=["DELETE"])
def delete_transaction(transaction_id):
    try:
        database = get_db()
        result = database.delete_transaction(transaction_id)
        if result:
            return cors_jsonify({"success": True, "message": "删除成功"})
        return cors_jsonify({"error": "删除失败"}, 500)
    except Exception as e:
        logger.error(f"Delete transaction error: {e}")
        return cors_jsonify({"error": str(e)}, 500)
