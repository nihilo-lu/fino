"""
Cloudflare D1 数据库管理器 - 基础设施层
通过 D1 HTTP REST API 连接，与 SQLiteManager 接口兼容
D1 基于 SQLite，SQL 语法兼容，使用 ? 占位符
"""

import json
import logging
import urllib.request
import urllib.error
from typing import Optional, Any, List, Tuple

# 默认汇率（相对于人民币）
DEFAULT_EXCHANGE_RATES = {
    "CNY": 1.0,
    "HKD": 0.92,
    "USD": 7.25,
    "EUR": 7.85,
    "GBP": 9.15,
    "JPY": 0.048,
}

D1_API_BASE = "https://api.cloudflare.com/client/v4"


def _d1_request(
    account_id: str,
    database_id: str,
    api_token: str,
    sql: str,
    params: Optional[tuple] = None,
) -> dict:
    """调用 D1 Query API"""
    url = f"{D1_API_BASE}/accounts/{account_id}/d1/database/{database_id}/query"
    body = {"sql": sql}
    if params:
        body["params"] = list(params)

    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_token}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode()
            err_data = json.loads(err_body) if err_body else {}
            msg = err_data.get("errors", [{}])[0].get("message", str(e)) if err_data.get("errors") else str(e)
        except Exception:
            msg = str(e)
        raise RuntimeError(f"D1 API 错误: {msg}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"D1 连接失败: {e.reason}") from e

    if not data.get("success"):
        errs = data.get("errors", [])
        msg = errs[0].get("message", "未知错误") if errs else "D1 查询失败"
        raise RuntimeError(f"D1 API 错误: {msg}")

    results = data.get("result", [])
    if not results:
        return {"meta": {"last_row_id": 0, "changes": 0}, "results": [], "success": True}
    return results[0]


class _D1Cursor:
    """D1 游标包装器，兼容 DB-API cursor"""

    def __init__(self, manager: "D1Manager"):
        self._manager = manager
        self._rows: List[tuple] = []
        self._row_index: int = 0
        self._description: Optional[List[tuple]] = None  # DB-API: (name, type_code, ...)
        self.lastrowid: Optional[int] = None
        self.rowcount: int = -1

    @property
    def description(self) -> Optional[List[tuple]]:
        """DB-API 列描述，供 pandas 等使用"""
        return self._description

    def execute(self, sql: str, params=None):
        # PRAGMA 在 D1 中部分支持，部分跳过
        sql_strip = sql.strip().upper()
        if sql_strip.startswith("PRAGMA"):
            self._rows = []
            self._row_index = 0
            self._description = None
            self.lastrowid = None
            self.rowcount = 0
            return self

        res = _d1_request(
            self._manager._account_id,
            self._manager._database_id,
            self._manager._api_token,
            sql,
            params if params else None,
        )
        meta = res.get("meta", {})
        self.lastrowid = meta.get("last_row_id") or 0
        self.rowcount = meta.get("changes", -1)

        raw = res.get("results") or []
        if raw:
            first = raw[0]
            if isinstance(first, dict):
                cols = list(first.keys())
                self._rows = [tuple(r.get(c) for c in cols) for r in raw]
                self._description = [(c, None, None, None, None, None, None) for c in cols]
            else:
                self._rows = [tuple(r) if isinstance(r, (list, tuple)) else (r,) for r in raw]
                self._description = [(f"column_{i}", None, None, None, None, None, None) for i in range(len(self._rows[0]) if self._rows else 0)]
        else:
            self._rows = []
            self._description = None
        self._row_index = 0
        return self

    def executemany(self, sql: str, params_list=None):
        params_list = params_list or []
        for params in params_list:
            self.execute(sql, params)
        return self

    def fetchone(self) -> Optional[tuple]:
        if self._row_index >= len(self._rows):
            return None
        row = self._rows[self._row_index]
        self._row_index += 1
        return row

    def fetchall(self) -> List[tuple]:
        rows = self._rows[self._row_index:]
        self._row_index = len(self._rows)
        return rows

    def fetchmany(self, size=None):
        size = size or 1
        end = min(self._row_index + size, len(self._rows))
        rows = self._rows[self._row_index:end]
        self._row_index = end
        return rows


class _D1Connection:
    """D1 连接包装器，兼容 DB-API connection"""

    def __init__(self, manager: "D1Manager"):
        self._manager = manager

    def cursor(self):
        return _D1Cursor(self._manager)

    def execute(self, sql: str, params=None):
        cur = self.cursor()
        cur.execute(sql, params)
        return cur

    def commit(self):
        pass  # D1 每个 query 默认提交

    def rollback(self):
        pass  # D1 无显式事务回滚

    def close(self):
        pass


class D1Manager:
    """Cloudflare D1 数据库管理器 - 与 SQLiteManager 接口兼容"""

    def __init__(
        self,
        account_id: str,
        database_id: str,
        api_token: str,
    ):
        if not account_id or not database_id or not api_token:
            raise ValueError("D1 需要 account_id、database_id 和 api_token")
        self._account_id = account_id
        self._database_id = database_id
        self._api_token = api_token
        self.conn: Optional[_D1Connection] = None
        self._connect()
        self._create_tables()
        self._init_default_data()

    def _connect(self):
        """建立连接（D1 为无状态 HTTP，仅创建包装器）"""
        self.conn = _D1Connection(self)

    def _execute(self, sql: str, params=None):
        return _d1_request(
            self._account_id,
            self._database_id,
            self._api_token,
            sql,
            params if params else None,
        )

    def _create_tables(self):
        """创建数据库表（SQLite 语法，D1 兼容）"""
        tables = [
            """CREATE TABLE IF NOT EXISTS ledgers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                cost_method TEXT DEFAULT 'FIFO',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                owner_username TEXT DEFAULT '',
                UNIQUE(owner_username, name)
            )""",
            """CREATE TABLE IF NOT EXISTS currencies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                symbol TEXT NOT NULL,
                exchange_rate REAL NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            """CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            """CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ledger_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                currency_id INTEGER NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ledger_id) REFERENCES ledgers(id),
                FOREIGN KEY (currency_id) REFERENCES currencies(id),
                UNIQUE(ledger_id, name)
            )""",
            """CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ledger_id INTEGER NOT NULL,
                account_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                type TEXT NOT NULL,
                category_id INTEGER NOT NULL,
                code TEXT NOT NULL,
                name TEXT NOT NULL,
                quantity REAL NOT NULL,
                price REAL NOT NULL,
                currency_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                amount_cny REAL NOT NULL,
                fee REAL DEFAULT 0,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ledger_id) REFERENCES ledgers(id),
                FOREIGN KEY (account_id) REFERENCES accounts(id),
                FOREIGN KEY (category_id) REFERENCES categories(id),
                FOREIGN KEY (currency_id) REFERENCES currencies(id)
            )""",
            """CREATE TABLE IF NOT EXISTS fund_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ledger_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                type TEXT NOT NULL,
                currency_id INTEGER NOT NULL,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ledger_id) REFERENCES ledgers(id),
                FOREIGN KEY (currency_id) REFERENCES currencies(id)
            )""",
            """CREATE TABLE IF NOT EXISTS fund_transaction_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fund_transaction_id INTEGER NOT NULL,
                account_id INTEGER NOT NULL,
                side TEXT NOT NULL CHECK(side IN ('debit', 'credit')),
                amount REAL NOT NULL,
                amount_cny REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (fund_transaction_id) REFERENCES fund_transactions(id) ON DELETE CASCADE,
                FOREIGN KEY (account_id) REFERENCES accounts(id)
            )""",
            """CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ledger_id INTEGER NOT NULL,
                account_id INTEGER NOT NULL,
                code TEXT NOT NULL,
                name TEXT NOT NULL,
                category_id INTEGER NOT NULL,
                currency_id INTEGER NOT NULL,
                quantity REAL NOT NULL,
                avg_cost REAL NOT NULL,
                current_price REAL NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ledger_id) REFERENCES ledgers(id),
                FOREIGN KEY (account_id) REFERENCES accounts(id),
                FOREIGN KEY (category_id) REFERENCES categories(id),
                FOREIGN KEY (currency_id) REFERENCES currencies(id),
                UNIQUE(ledger_id, account_id, code)
            )""",
        ]
        for sql in tables:
            self._execute(sql)

        self._migrate_database()

    def _migrate_database(self):
        """数据库迁移：检查并添加缺失的列"""
        try:
            res = self._execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='ledgers'"
            )
            rows = res.get("results") or []
            if not rows:
                return
        except Exception:
            return

        try:
            res = self._execute("PRAGMA table_info(ledgers)")
            cols_raw = res.get("results") or []
            columns = []
            for r in cols_raw:
                if isinstance(r, dict):
                    columns.append(r.get("name", ""))
                elif isinstance(r, (list, tuple)) and len(r) > 1:
                    columns.append(r[1])
                else:
                    columns.append("")
        except Exception:
            columns = []

        if "cost_method" not in columns:
            logging.info("迁移 D1：为 ledgers 表添加 cost_method 列")
            self._execute("ALTER TABLE ledgers ADD COLUMN cost_method TEXT DEFAULT 'FIFO'")

        if "owner_username" not in columns:
            logging.info("迁移 D1：为 ledgers 表添加 owner_username 列")
            self._execute("ALTER TABLE ledgers ADD COLUMN owner_username TEXT DEFAULT ''")

        try:
            res = self._execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='categories'"
            )
            if not res.get("results"):
                for cat_name, cat_desc in [
                    ("股票", "股票投资"),
                    ("基金", "基金投资"),
                    ("债券", "债券投资"),
                    ("加密货币", "加密货币投资"),
                    ("银行理财", "银行理财产品"),
                    ("其他", "其他投资类型"),
                ]:
                    self._execute(
                        "INSERT OR IGNORE INTO categories (name, description) VALUES (?, ?)",
                        (cat_name, cat_desc),
                    )
        except Exception:
            pass

    def _init_default_data(self):
        """初始化默认数据"""
        # 检查是否已有 CNY
        try:
            res = self._execute("SELECT id FROM currencies WHERE code = 'CNY'")
            if res.get("results"):
                return
        except Exception:
            pass
        for code, name, symbol, rate in [
            ("CNY", "人民币", "¥", 1.0),
            ("USD", "美元", "$", 7.25),
            ("HKD", "港币", "HK$", 0.92),
            ("EUR", "欧元", "€", 7.85),
            ("GBP", "英镑", "£", 9.15),
            ("JPY", "日元", "¥", 0.048),
        ]:
            try:
                self._execute(
                    "INSERT OR IGNORE INTO currencies (code, name, symbol, exchange_rate) VALUES (?, ?, ?, ?)",
                    (code, name, symbol, rate),
                )
            except Exception:
                pass
        # 默认投资类别
        for cat_name, cat_desc in [
            ("股票", "股票投资"),
            ("基金", "基金投资"),
            ("债券", "债券投资"),
            ("加密货币", "加密货币投资"),
            ("银行理财", "银行理财产品"),
            ("其他", "其他投资类型"),
        ]:
            try:
                self._execute(
                    "INSERT OR IGNORE INTO categories (name, description) VALUES (?, ?)",
                    (cat_name, cat_desc),
                )
            except Exception:
                pass

    def get_connection(self) -> _D1Connection:
        """获取数据库连接"""
        if self.conn is None:
            self._connect()
        return self.conn

    def close(self):
        """关闭连接（D1 无状态，无实际操作）"""
        self.conn = None
