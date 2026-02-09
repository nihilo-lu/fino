"""
投资追踪器 API 服务器
提供 REST API 接口，供前端调用后端业务逻辑

启动方式:
    python api_server.py

默认端口: 8080
"""

import os
import sys
import json
import logging
from datetime import datetime
from functools import wraps
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

sys.path.insert(0, os.path.dirname(__file__))

from database import Database
from utils.auth_config import load_config, save_config
import yaml
from yaml.loader import SafeLoader

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='frontend', static_url_path='/frontend')
CORS(app)

config_path = os.path.join(os.path.dirname(__file__), "conf", "config.yaml")

db = None

def get_db():
    global db
    if db is None:
        db = Database(config_path=config_path)
    return db

def json_default(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

def cors_jsonify(data, status=200):
    response = jsonify(data)
    response.status_code = status
    return response

@app.route('/api/health', methods=['GET'])
def health_check():
    return cors_jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return cors_jsonify({"error": "用户名和密码不能为空"}, 400)
    
    try:
        config = load_config(config_path)
        usernames = config.get("credentials", {}).get("usernames", {})
        
        if username not in usernames:
            return cors_jsonify({"error": "用户名或密码错误"}, 401)
        
        user = usernames[username]
        import bcrypt
        if bcrypt.checkpw(password.encode('utf-8'), user.get('password', '').encode('utf-8')):
            return cors_jsonify({
                "success": True,
                "username": username,
                "name": user.get('first_name', '') or username,
                "email": user.get('email', ''),
                "roles": user.get('roles', [])
            })
        else:
            return cors_jsonify({"error": "用户名或密码错误"}, 401)
    except Exception as e:
        logger.error(f"Login error: {e}")
        return cors_jsonify({"error": f"登录失败: {str(e)}"}, 500)

@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.get_json()
    email = data.get('email', '').strip()
    username = data.get('username', '').strip().lower()
    password = data.get('password', '').strip()
    password_repeat = data.get('password_repeat', '').strip()
    password_hint = data.get('password_hint', '').strip() or None
    
    if not all([email, username, password, password_repeat]):
        return cors_jsonify({"error": "所有字段都为必填项"}, 400)
    
    if password != password_repeat:
        return cors_jsonify({"error": "两次输入的密码不一致"}, 400)
    
    import re
    if not re.match(r"^[^@]+@[^@]+\.[^@]+$", email):
        return cors_jsonify({"error": "邮箱格式不正确"}, 400)
    
    try:
        config = load_config(config_path)
        usernames = config.get("credentials", {}).get("usernames", {})
        
        if username in usernames:
            return cors_jsonify({"error": "用户名已被使用"}, 400)
        
        import bcrypt
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        usernames[username] = {
            "email": email,
            "first_name": "",
            "last_name": "",
            "password": hashed_password,
            "password_hint": password_hint,
            "roles": [],
            "failed_login_attempts": 0,
            "logged_in": False,
        }
        
        config["credentials"]["usernames"] = usernames
        
        if save_config(config_path, config):
            return cors_jsonify({"success": True, "message": "注册成功"})
        else:
            return cors_jsonify({"error": "保存配置失败"}, 500)
    except Exception as e:
        logger.error(f"Register error: {e}")
        return cors_jsonify({"error": f"注册失败: {str(e)}"}, 500)

@app.route('/api/ledgers', methods=['GET'])
def get_ledgers():
    username = request.args.get('username')
    if not username:
        return cors_jsonify({"error": "需要用户名参数"}, 400)
    
    try:
        database = get_db()
        ledgers = database.get_ledgers(username)
        ledgers_list = ledgers.to_dict(orient='records') if not ledgers.empty else []
        return cors_jsonify({"ledgers": ledgers_list})
    except Exception as e:
        logger.error(f"Get ledgers error: {e}")
        return cors_jsonify({"error": str(e)}, 500)

@app.route('/api/ledgers', methods=['POST'])
def create_ledger():
    data = request.get_json()
    username = data.get('username')
    name = data.get('name')
    description = data.get('description', '')
    cost_method = data.get('cost_method', 'FIFO')
    
    if not all([username, name]):
        return cors_jsonify({"error": "用户名和账本名称为必填"}, 400)
    
    try:
        database = get_db()
        result = database.add_ledger(name, description, cost_method, username)
        if result:
            return cors_jsonify({"success": True, "message": "账本创建成功"})
        else:
            return cors_jsonify({"error": "创建账本失败"}, 500)
    except Exception as e:
        logger.error(f"Create ledger error: {e}")
        return cors_jsonify({"error": str(e)}, 500)

@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    ledger_id = request.args.get('ledger_id', type=int)
    try:
        database = get_db()
        accounts = database.get_accounts(ledger_id)
        accounts_list = accounts.to_dict(orient='records') if not accounts.empty else []
        return cors_jsonify({"accounts": accounts_list})
    except Exception as e:
        logger.error(f"Get accounts error: {e}")
        return cors_jsonify({"error": str(e)}, 500)

@app.route('/api/accounts', methods=['POST'])
def create_account():
    data = request.get_json()
    ledger_id = data.get('ledger_id')
    name = data.get('name')
    acc_type = data.get('type')
    currency = data.get('currency', 'CNY')
    description = data.get('description', '')
    
    if not all([ledger_id, name, acc_type]):
        return cors_jsonify({"error": "账本ID、账户名称和类型为必填"}, 400)
    
    try:
        database = get_db()
        result = database.add_account(ledger_id, name, acc_type, currency, description)
        if result:
            return cors_jsonify({"success": True, "message": "账户创建成功"})
        else:
            return cors_jsonify({"error": "创建账户失败"}, 500)
    except Exception as e:
        logger.error(f"Create account error: {e}")
        return cors_jsonify({"error": str(e)}, 500)

@app.route('/api/portfolio/stats', methods=['GET'])
def get_portfolio_stats():
    ledger_id = request.args.get('ledger_id', type=int)
    account_id = request.args.get('account_id', type=int)
    
    try:
        database = get_db()
        stats = database.get_portfolio_stats(ledger_id, account_id)
        return cors_jsonify({"stats": stats})
    except Exception as e:
        logger.error(f"Get portfolio stats error: {e}")
        return cors_jsonify({"error": str(e)}, 500)

@app.route('/api/positions', methods=['GET'])
def get_positions():
    ledger_id = request.args.get('ledger_id', type=int)
    account_id = request.args.get('account_id', type=int)
    
    try:
        database = get_db()
        positions = database.get_positions(ledger_id, account_id)
        positions_list = positions.to_dict(orient='records') if not positions.empty else []
        return cors_jsonify({"positions": positions_list})
    except Exception as e:
        logger.error(f"Get positions error: {e}")
        return cors_jsonify({"error": str(e)}, 500)

@app.route('/api/transactions', methods=['GET'])
def get_transactions():
    ledger_id = request.args.get('ledger_id', type=int)
    account_id = request.args.get('account_id', type=int)
    trans_type = request.args.get('type')
    category = request.args.get('category')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    limit = request.args.get('limit', type=int, default=50)
    offset = request.args.get('offset', type=int, default=0)
    
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
            offset=offset
        )
        transactions_list = transactions.to_dict(orient='records') if not transactions.empty else []
        
        total_count = database.get_transactions_count(
            ledger_id=ledger_id,
            account_id=account_id,
            trans_type=trans_type,
            category=category,
            start_date=start_date,
            end_date=end_date
        )
        
        return cors_jsonify({
            "transactions": transactions_list,
            "total": total_count,
            "limit": limit,
            "offset": offset
        })
    except Exception as e:
        logger.error(f"Get transactions error: {e}")
        return cors_jsonify({"error": str(e)}, 500)

@app.route('/api/transactions', methods=['POST'])
def create_transaction():
    data = request.get_json()
    
    required_fields = ['ledger_id', 'account_id', 'type', 'code', 'name', 'date']
    if not all(data.get(f) for f in required_fields):
        return cors_jsonify({"error": "缺少必填字段"}, 400)
    
    try:
        database = get_db()
        transaction = {
            'ledger_id': data.get('ledger_id'),
            'account_id': data.get('account_id'),
            'type': data.get('type'),
            'code': data.get('code'),
            'name': data.get('name'),
            'date': data.get('date'),
            'price': data.get('price'),
            'quantity': data.get('quantity'),
            'amount': data.get('amount'),
            'fee': data.get('fee', 0),
            'category': data.get('category'),
            'notes': data.get('notes', ''),
        }
        
        result = database.add_transaction(transaction)
        if result:
            return cors_jsonify({"success": True, "message": "交易记录添加成功"})
        else:
            return cors_jsonify({"error": "添加交易记录失败"}, 500)
    except Exception as e:
        logger.error(f"Create transaction error: {e}")
        return cors_jsonify({"error": str(e)}, 500)

@app.route('/api/fund-transactions', methods=['GET'])
def get_fund_transactions():
    ledger_id = request.args.get('ledger_id', type=int)
    account_id = request.args.get('account_id', type=int)
    trans_type = request.args.get('type')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    limit = request.args.get('limit', type=int, default=50)
    offset = request.args.get('offset', type=int, default=0)
    
    try:
        database = get_db()
        fund_transactions = database.get_fund_transactions(
            ledger_id=ledger_id,
            account_id=account_id,
            trans_type=trans_type,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset
        )
        fund_list = fund_transactions.to_dict(orient='records') if not fund_transactions.empty else []
        
        return cors_jsonify({
            "fund_transactions": fund_list,
            "limit": limit,
            "offset": offset
        })
    except Exception as e:
        logger.error(f"Get fund transactions error: {e}")
        return cors_jsonify({"error": str(e)}, 500)

@app.route('/api/fund-transactions', methods=['POST'])
def create_fund_transaction():
    data = request.get_json()
    
    required_fields = ['ledger_id', 'account_id', 'type', 'date']
    if not all(data.get(f) for f in required_fields):
        return cors_jsonify({"error": "缺少必填字段"}, 400)
    
    try:
        database = get_db()
        fund_trans = {
            'ledger_id': data.get('ledger_id'),
            'account_id': data.get('account_id'),
            'type': data.get('type'),
            'date': data.get('date'),
            'amount': data.get('amount'),
            'currency': data.get('currency', 'CNY'),
            'exchange_rate': data.get('exchange_rate', 1.0),
            'amount_cny': data.get('amount_cny'),
            'description': data.get('description', ''),
        }
        
        result = database.add_fund_transaction(fund_trans)
        if result:
            return cors_jsonify({"success": True, "message": "资金明细添加成功"})
        else:
            return cors_jsonify({"error": "添加资金明细失败"}, 500)
    except Exception as e:
        logger.error(f"Create fund transaction error: {e}")
        return cors_jsonify({"error": str(e)}, 500)

@app.route('/api/categories', methods=['GET'])
def get_categories():
    try:
        database = get_db()
        categories = database.get_categories()
        categories_list = categories.to_dict(orient='records') if not categories.empty else []
        return cors_jsonify({"categories": categories_list})
    except Exception as e:
        logger.error(f"Get categories error: {e}")
        return cors_jsonify({"error": str(e)}, 500)

@app.route('/api/currencies', methods=['GET'])
def get_currencies():
    try:
        database = get_db()
        currencies = database.get_currencies()
        currencies_list = currencies.to_dict(orient='records') if not currencies.empty else []
        return cors_jsonify({"currencies": currencies_list})
    except Exception as e:
        logger.error(f"Get currencies error: {e}")
        return cors_jsonify({"error": str(e)}, 500)

@app.route('/api/market/price', methods=['POST'])
def fetch_market_price():
    data = request.get_json()
    code = data.get('code')
    
    if not code:
        return cors_jsonify({"error": "股票代码为必填"}, 400)
    
    try:
        database = get_db()
        price = database.fetch_market_price(code)
        if price is not None:
            return cors_jsonify({"success": True, "price": price})
        else:
            return cors_jsonify({"error": "无法获取价格"}, 500)
    except Exception as e:
        logger.error(f"Fetch market price error: {e}")
        return cors_jsonify({"error": str(e)}, 500)

@app.route('/api/exchange-rate', methods=['POST'])
def fetch_exchange_rate():
    data = request.get_json()
    currency = data.get('currency')
    
    if not currency:
        return cors_jsonify({"error": "币种代码为必填"}, 400)
    
    try:
        database = get_db()
        rate = database.fetch_exchange_rate_from_market(currency)
        if rate is not None:
            return cors_jsonify({"success": True, "rate": rate})
        else:
            return cors_jsonify({"error": "无法获取汇率"}, 500)
    except Exception as e:
        logger.error(f"Fetch exchange rate error: {e}")
        return cors_jsonify({"error": str(e)}, 500)

@app.route('/api/analysis/returns', methods=['GET'])
def get_returns_analysis():
    ledger_id = request.args.get('ledger_id', type=int)
    account_id = request.args.get('account_id', type=int)
    
    try:
        database = get_db()
        return_rate = database.get_latest_cumulative_return(ledger_id)
        portfolio_stats = database.get_portfolio_stats(ledger_id, account_id)
        
        return cors_jsonify({
            "cumulative_return": return_rate,
            "portfolio_stats": portfolio_stats
        })
    except Exception as e:
        logger.error(f"Get returns analysis error: {e}")
        return cors_jsonify({"error": str(e)}, 500)

@app.route('/api/transactions/<int:transaction_id>', methods=['DELETE'])
def delete_transaction(transaction_id):
    try:
        database = get_db()
        result = database.delete_transaction(transaction_id)
        if result:
            return cors_jsonify({"success": True, "message": "删除成功"})
        else:
            return cors_jsonify({"error": "删除失败"}, 500)
    except Exception as e:
        logger.error(f"Delete transaction error: {e}")
        return cors_jsonify({"error": str(e)}, 500)

@app.route('/api/positions/<int:position_id>', methods=['DELETE'])
def delete_position(position_id):
    try:
        database = get_db()
        cursor = database.conn.cursor()
        cursor.execute("DELETE FROM positions WHERE id = ?", (position_id,))
        database.conn.commit()
        return cors_jsonify({"success": True, "message": "删除成功"})
    except Exception as e:
        logger.error(f"Delete position error: {e}")
        return cors_jsonify({"error": str(e)}, 500)

@app.route('/')
def index():
    return send_from_directory('frontend', 'index.html')

@app.route('/frontend/<path:filename>')
def serve_static(filename):
    return send_from_directory('frontend', filename)

if __name__ == '__main__':
    print("=" * 60)
    print("  投资追踪器 API 服务器")
    print("  地址: http://localhost:8080")
    print("  前端: http://localhost:8080/")
    print("=" * 60)
    app.run(host='0.0.0.0', port=8080, debug=True)
