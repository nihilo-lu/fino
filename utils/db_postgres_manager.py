"""
PostgreSQL 数据库管理器 - 基础设施层
与 SQLiteManager 接口兼容，支持多数据库架构
"""

import re
import logging
from typing import Optional, Any, List, Tuple

from utils.default_currencies import get_all_default_currencies, get_currency_info


def _convert_sql_sqlite_to_pg(sql: str) -> str:
    """将 SQLite 风格 SQL 转换为 PostgreSQL 风格"""
    # sqlite_master 表检查 -> information_schema（PostgreSQL 无 sqlite_master）
    if 'sqlite_master' in sql.lower():
        m = re.search(r"name\s*=\s*['\"]([^'\"]+)['\"]", sql, re.I)
        table_name = m.group(1) if m else ""
        if table_name:
            sql = f"SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='{table_name}'"
    # 占位符 ? -> %s
    sql = sql.replace('?', '%s')
    # INSERT OR IGNORE -> INSERT ... ON CONFLICT DO NOTHING
    if 'INSERT OR IGNORE' in sql.upper():
        sql = re.sub(r'INSERT\s+OR\s+IGNORE\s+INTO', 'INSERT INTO', sql, flags=re.I)
        sql = sql.rstrip(';').rstrip()
        if 'ON CONFLICT' not in sql.upper():
            if 'security_price_history' in sql:
                sql += ' ON CONFLICT (date, code) DO NOTHING'
            elif 'exchange_rate_history' in sql:
                sql += ' ON CONFLICT (date, currency_code) DO NOTHING'
            elif 'account_balance_history' in sql:
                sql += ' ON CONFLICT (date, account_id) DO UPDATE SET balance_cny = EXCLUDED.balance_cny'
            elif 'currencies' in sql:
                sql += ' ON CONFLICT (code) DO NOTHING'
    # INSERT OR REPLACE -> INSERT ... ON CONFLICT DO UPDATE
    if 'INSERT OR REPLACE' in sql.upper():
        sql = re.sub(r'INSERT\s+OR\s+REPLACE\s+INTO', 'INSERT INTO', sql, flags=re.I)
        sql = sql.rstrip(';').rstrip()
        if 'ON CONFLICT' not in sql.upper():
            if 'account_balance_history' in sql:
                sql += ' ON CONFLICT (date, account_id) DO UPDATE SET balance_cny = EXCLUDED.balance_cny'
            elif 'return_rate' in sql:
                sql += ' ON CONFLICT (date, ledger_id) DO UPDATE SET "发生金额"=EXCLUDED."发生金额","确认份额"=EXCLUDED."确认份额","确认净值"=EXCLUDED."确认净值","总份额"=EXCLUDED."总份额","单位净值"=EXCLUDED."单位净值","当日净资产"=EXCLUDED."当日净资产","当日损益"=EXCLUDED."当日损益","当日收益率"=EXCLUDED."当日收益率","累计收益率"=EXCLUDED."累计收益率","总资产"=EXCLUDED."总资产","账本"=EXCLUDED."账本",updated_at=CURRENT_TIMESTAMP'
            elif 'rounding_diff' in sql:
                sql += ' ON CONFLICT (date, ledger_id) DO UPDATE SET "原始份额"=EXCLUDED."原始份额","确认份额"=EXCLUDED."确认份额","尾差份额"=EXCLUDED."尾差份额","尾差金额"=EXCLUDED."尾差金额","确认净值"=EXCLUDED."确认净值","账本"=EXCLUDED."账本","备注"=EXCLUDED."备注",updated_at=CURRENT_TIMESTAMP'
    return sql


class _PGCursorWrapper:
    """PostgreSQL 游标包装器：将 ? 转为 %s，并为 INSERT 支持 lastrowid"""

    def __init__(self, real_cursor):
        self._cursor = real_cursor
        self.lastrowid = None

    def execute(self, sql: str, params=None):
        # PostgreSQL 不支持 PRAGMA，直接跳过
        if sql.strip().upper().startswith('PRAGMA'):
            return self
        sql = _convert_sql_sqlite_to_pg(sql)
        # 对于 INSERT 语句（非 OR IGNORE/ON CONFLICT），添加 RETURNING id 以支持 lastrowid
        sql_upper = sql.strip().upper()
        if (sql_upper.startswith('INSERT INTO') and 'RETURNING' not in sql.upper()
                and 'ON CONFLICT' not in sql.upper()):
            # 在 VALUES 或 SELECT 子句后、分号前插入 RETURNING id
            sql = sql.rstrip(';').rstrip()
            sql += ' RETURNING id'
        self._cursor.execute(sql, params or ())
        if 'RETURNING' in sql.upper():
            row = self._cursor.fetchone()
            self.lastrowid = row[0] if row else None
        elif sql_upper.startswith('INSERT'):
            try:
                self._cursor.execute("SELECT lastval()")
                row = self._cursor.fetchone()
                self.lastrowid = row[0] if row else None
            except Exception:
                self.lastrowid = None
        return self

    def executemany(self, sql: str, params_list=None):
        sql = _convert_sql_sqlite_to_pg(sql)
        return self._cursor.executemany(sql, params_list or [])

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def fetchmany(self, size=None):
        return self._cursor.fetchmany(size)

    @property
    def rowcount(self):
        return self._cursor.rowcount

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class _PGConnectionWrapper:
    """PostgreSQL 连接包装器：返回包装后的游标，使 ? 占位符和 lastrowid 兼容"""

    def __init__(self, real_conn):
        self._conn = real_conn

    def cursor(self):
        return _PGCursorWrapper(self._conn.cursor())

    def execute(self, sql, params=None):
        """支持 pandas read_sql_query 等直接调用 connection.execute"""
        cur = self.cursor()
        cur.execute(sql, params)
        return cur

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        return self._conn.close()

    def __getattr__(self, name):
        return getattr(self._conn, name)


class PostgreSQLManager:
    """PostgreSQL 数据库管理器 - 与 SQLiteManager 接口兼容"""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        database: str = "investment",
        user: str = "postgres",
        password: str = "",
        sslmode: str = "prefer",
        config_path: Optional[str] = None,
    ):
        try:
            import psycopg2
        except ImportError:
            raise ImportError("使用 PostgreSQL 需要安装 psycopg2: pip install psycopg2-binary")

        self._host = host
        self._port = port
        self._database = database
        self._user = user
        self._password = password
        self._sslmode = sslmode
        self.config_path = config_path
        self.conn: Optional[Any] = None
        self._psycopg2 = psycopg2
        self._connect()
        self._create_tables()
        self._init_default_data()

    def _connect(self):
        """建立数据库连接"""
        self.conn = _PGConnectionWrapper(
            self._psycopg2.connect(
                host=self._host,
                port=self._port,
                dbname=self._database,
                user=self._user,
                password=self._password,
                sslmode=self._sslmode,
            )
        )

    def _create_tables(self):
        """创建数据库表（PostgreSQL 语法）"""
        cursor = self.conn.cursor()

        # 币种表（需先创建，因 accounts 等依赖）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS currencies (
                id SERIAL PRIMARY KEY,
                code VARCHAR(20) UNIQUE NOT NULL,
                name VARCHAR(100) NOT NULL,
                symbol VARCHAR(10) NOT NULL,
                exchange_rate DOUBLE PRECISION NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'currencies'")
        if cursor.fetchone():
            pass  # 表已存在

        # 账本表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ledgers (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                cost_method VARCHAR(20) DEFAULT 'FIFO',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                owner_username VARCHAR(255) DEFAULT '',
                UNIQUE(owner_username, name)
            )
        ''')

        # 投资类别表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS categories (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) UNIQUE NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 账户表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS accounts (
                id SERIAL PRIMARY KEY,
                ledger_id INTEGER NOT NULL REFERENCES ledgers(id),
                name VARCHAR(255) NOT NULL,
                type VARCHAR(50) NOT NULL,
                currency_id INTEGER NOT NULL REFERENCES currencies(id),
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ledger_id, name)
            )
        ''')

        # 交易记录表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id SERIAL PRIMARY KEY,
                ledger_id INTEGER NOT NULL REFERENCES ledgers(id),
                account_id INTEGER NOT NULL REFERENCES accounts(id),
                date VARCHAR(20) NOT NULL,
                type VARCHAR(50) NOT NULL,
                category_id INTEGER NOT NULL REFERENCES categories(id),
                code VARCHAR(50) NOT NULL,
                name VARCHAR(255) NOT NULL,
                quantity DOUBLE PRECISION NOT NULL,
                price DOUBLE PRECISION NOT NULL,
                currency_id INTEGER NOT NULL REFERENCES currencies(id),
                amount DOUBLE PRECISION NOT NULL,
                amount_cny DOUBLE PRECISION NOT NULL,
                fee DOUBLE PRECISION DEFAULT 0,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 资金明细表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS fund_transactions (
                id SERIAL PRIMARY KEY,
                ledger_id INTEGER NOT NULL REFERENCES ledgers(id),
                date VARCHAR(20) NOT NULL,
                type VARCHAR(50) NOT NULL,
                currency_id INTEGER NOT NULL REFERENCES currencies(id),
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                transaction_id INTEGER REFERENCES transactions(id)
            )
        ''')

        # 借贷分录明细表（每笔分录可有独立币种，支持人民币借、港币贷等）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS fund_transaction_entries (
                id SERIAL PRIMARY KEY,
                fund_transaction_id INTEGER NOT NULL REFERENCES fund_transactions(id) ON DELETE CASCADE,
                account_id INTEGER NOT NULL REFERENCES accounts(id),
                side VARCHAR(10) NOT NULL CHECK(side IN ('debit', 'credit')),
                amount DOUBLE PRECISION NOT NULL,
                amount_cny DOUBLE PRECISION NOT NULL,
                currency_id INTEGER REFERENCES currencies(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                subject_type VARCHAR(20) DEFAULT 'cash'
            )
        ''')
        # 迁移：为已有表添加 currency_id 并回填（兼容无该列的老库）
        try:
            cursor.execute('''
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'fund_transaction_entries' AND column_name = 'currency_id'
            ''')
            if not cursor.fetchone():
                cursor.execute('''
                    ALTER TABLE fund_transaction_entries
                    ADD COLUMN currency_id INTEGER REFERENCES currencies(id)
                ''')
            cursor.execute('''
                UPDATE fund_transaction_entries fte
                SET currency_id = ft.currency_id
                FROM fund_transactions ft
                WHERE fte.fund_transaction_id = ft.id AND fte.currency_id IS NULL
            ''')
        except Exception as e:
            logging.getLogger(__name__).debug("fund_transaction_entries currency_id migration: %s", e)

        # 持仓表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS positions (
                id SERIAL PRIMARY KEY,
                ledger_id INTEGER NOT NULL REFERENCES ledgers(id),
                account_id INTEGER NOT NULL REFERENCES accounts(id),
                code VARCHAR(50) NOT NULL,
                name VARCHAR(255) NOT NULL,
                category_id INTEGER NOT NULL REFERENCES categories(id),
                currency_id INTEGER NOT NULL REFERENCES currencies(id),
                quantity DOUBLE PRECISION NOT NULL,
                avg_cost DOUBLE PRECISION NOT NULL,
                current_price DOUBLE PRECISION NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ledger_id, account_id, code)
            )
        ''')

        # 历史价格与快照表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS security_price_history (
                date VARCHAR(20) NOT NULL,
                code VARCHAR(50) NOT NULL,
                price DOUBLE PRECISION NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (date, code)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS exchange_rate_history (
                date VARCHAR(20) NOT NULL,
                currency_code VARCHAR(20) NOT NULL,
                rate DOUBLE PRECISION NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (date, currency_code)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS position_history (
                id SERIAL PRIMARY KEY,
                date VARCHAR(20) NOT NULL,
                ledger_id INTEGER NOT NULL REFERENCES ledgers(id),
                account_id INTEGER NOT NULL REFERENCES accounts(id),
                code VARCHAR(50) NOT NULL,
                name VARCHAR(255) NOT NULL,
                category_id INTEGER NOT NULL REFERENCES categories(id),
                currency_id INTEGER NOT NULL REFERENCES currencies(id),
                quantity DOUBLE PRECISION NOT NULL,
                avg_cost DOUBLE PRECISION NOT NULL,
                price_at_date DOUBLE PRECISION NOT NULL,
                market_value_local DOUBLE PRECISION NOT NULL,
                rate_at_date DOUBLE PRECISION NOT NULL,
                market_value_cny DOUBLE PRECISION NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_position_history_date_ledger_account
            ON position_history(date, ledger_id, account_id)
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS return_rate (
                id SERIAL PRIMARY KEY,
                date VARCHAR(20) NOT NULL,
                ledger_id INTEGER NOT NULL REFERENCES ledgers(id),
                "发生金额" DOUBLE PRECISION,
                "确认份额" DOUBLE PRECISION,
                "确认净值" DOUBLE PRECISION,
                "总份额" DOUBLE PRECISION,
                "单位净值" DOUBLE PRECISION,
                "当日净资产" DOUBLE PRECISION,
                "当日损益" DOUBLE PRECISION,
                "当日收益率" TEXT,
                "累计收益率" DOUBLE PRECISION,
                "总资产" DOUBLE PRECISION,
                "账本" VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(date, ledger_id)
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_return_rate_date ON return_rate(date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_return_rate_ledger ON return_rate(ledger_id)')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS rounding_diff (
                id SERIAL PRIMARY KEY,
                date VARCHAR(20) NOT NULL,
                ledger_id INTEGER NOT NULL REFERENCES ledgers(id),
                "原始份额" DOUBLE PRECISION,
                "确认份额" DOUBLE PRECISION,
                "尾差份额" DOUBLE PRECISION,
                "尾差金额" DOUBLE PRECISION,
                "确认净值" DOUBLE PRECISION,
                "账本" VARCHAR(255),
                "备注" TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(date, ledger_id)
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_rounding_diff_date ON rounding_diff(date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_rounding_diff_ledger ON rounding_diff(ledger_id)')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS account_balance_history (
                date VARCHAR(20) NOT NULL,
                account_id INTEGER NOT NULL REFERENCES accounts(id),
                balance_cny DOUBLE PRECISION NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (date, account_id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cloudreve_bindings (
                id SERIAL PRIMARY KEY,
                username VARCHAR(255) NOT NULL UNIQUE,
                cloudreve_url TEXT NOT NULL,
                access_token TEXT NOT NULL,
                refresh_token TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cloudreve_bindings_username ON cloudreve_bindings(username)')

        self.conn.commit()

    def _init_default_data(self):
        """初始化默认数据，币种与汇率使用设置中的默认值"""
        cursor = self.conn.cursor()
        for code, name, symbol, rate in get_all_default_currencies(self.config_path):
            cursor.execute('''
                INSERT INTO currencies (code, name, symbol, exchange_rate)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (code) DO NOTHING
            ''', (code, name, symbol, rate))

        cursor.execute('SELECT COUNT(*) FROM categories')
        category_count = cursor.fetchone()[0]
        if category_count == 0:
            default_categories = [
                ('股票', '股票投资'),
                ('基金', '基金投资'),
                ('债券', '债券投资'),
                ('加密货币', '加密货币投资'),
                ('银行理财', '银行理财产品'),
                ('其他', '其他投资类型'),
            ]
            for cat_name, cat_desc in default_categories:
                cursor.execute('''
                    INSERT INTO categories (name, description)
                    VALUES (%s, %s)
                ''', (cat_name, cat_desc))

        self.conn.commit()

    def ensure_currency_exists(self, code: str) -> None:
        """若该币种不存在则插入（使用设置中的默认汇率），PostgreSQL 使用 ON CONFLICT DO NOTHING。"""
        if not (code and str(code).strip()):
            return
        code = str(code).strip().upper()
        cursor = self.conn.cursor()
        cursor.execute("SELECT id FROM currencies WHERE code = %s LIMIT 1", (code,))
        if cursor.fetchone():
            return
        name, symbol, rate = get_currency_info(code, self.config_path)
        cursor.execute('''
            INSERT INTO currencies (code, name, symbol, exchange_rate)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (code) DO NOTHING
        ''', (code, name, symbol, rate))
        self.conn.commit()

    def get_connection(self):
        """获取数据库连接（已包装，支持 ? 占位符和 lastrowid）"""
        if self.conn is None:
            self._connect()
        return self.conn

    def close(self):
        """关闭数据库连接"""
        if self.conn:
            try:
                self.conn.close()
            except Exception:
                pass
            self.conn = None
