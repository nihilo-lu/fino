"""
SQLite 数据库管理器 - 基础设施层
负责数据库连接、表结构创建、数据库迁移和初始化
"""

import sqlite3
import logging
from typing import Optional

from utils.default_currencies import get_all_default_currencies, get_currency_info


class SQLiteManager:
    """SQLite 数据库管理器 - 基础设施层"""

    def __init__(self, db_path: str = "investment.db", config_path: Optional[str] = None):
        """初始化数据库连接

        Args:
            db_path: 数据库文件路径
            config_path: 配置文件路径，用于读取 default_exchange_rates 等设置（可选）
        """
        self.db_path = db_path
        self.config_path = config_path
        self.conn: Optional[sqlite3.Connection] = None
        self._connect()
        self._create_tables()
        self._init_default_data()

    def _connect(self):
        """建立数据库连接"""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        # 启用外键约束
        self.conn.execute("PRAGMA foreign_keys = ON")

    def _create_tables(self):
        """创建数据库表"""
        cursor = self.conn.cursor()

        # 账本表（用户/家庭成员）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ledgers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                cost_method TEXT DEFAULT 'FIFO',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 账户表（银行、券商等）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
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
            )
        """)

        # 币种表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS currencies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                symbol TEXT NOT NULL,
                exchange_rate REAL NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 投资类别表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 交易记录表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
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
            )
        """)

        # 资金明细表（借贷记账法）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fund_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ledger_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                type TEXT NOT NULL,
                currency_id INTEGER NOT NULL,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ledger_id) REFERENCES ledgers(id),
                FOREIGN KEY (currency_id) REFERENCES currencies(id)
            )
        """)

        # 借贷分录明细表（支持多借多贷）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fund_transaction_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fund_transaction_id INTEGER NOT NULL,
                account_id INTEGER NOT NULL,
                side TEXT NOT NULL CHECK(side IN ('debit', 'credit')),
                amount REAL NOT NULL,
                amount_cny REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (fund_transaction_id) REFERENCES fund_transactions(id) ON DELETE CASCADE,
                FOREIGN KEY (account_id) REFERENCES accounts(id)
            )
        """)

        # 持仓表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS positions (
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
            )
        """)

        # 数据库迁移：检查并添加缺失的列
        self._migrate_database(cursor)

        self.conn.commit()

    def _migrate_database(self, cursor):
        """数据库迁移：检查并添加缺失的列和表"""
        # 检查 ledgers 表是否有 cost_method 列
        cursor.execute("PRAGMA table_info(ledgers)")
        columns = [col[1] for col in cursor.fetchall()]

        if "cost_method" not in columns:
            logging.info("迁移数据库：为 ledgers 表添加 cost_method 列")
            cursor.execute(
                "ALTER TABLE ledgers ADD COLUMN cost_method TEXT DEFAULT 'FIFO'"
            )

        # 多用户数据隔离：为 ledgers 添加 owner_username 并改为 (owner_username, name) 唯一
        if "owner_username" not in columns:
            logging.info(
                "迁移数据库：为 ledgers 表添加 owner_username 列（多用户隔离）"
            )
            cursor.execute(
                "ALTER TABLE ledgers ADD COLUMN owner_username TEXT DEFAULT ''"
            )
            columns = columns + ["owner_username"]
        # 重建 ledgers 表：将 UNIQUE(name) 改为 UNIQUE(owner_username, name)，使不同用户可有同名账本
        cursor.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='ledgers'"
        )
        row = cursor.fetchone()
        create_sql = (row[0] or "").upper()
        if (
            create_sql
            and "UNIQUE(OWNER_USERNAME" not in create_sql
            and "UNIQUE (OWNER_USERNAME" not in create_sql
        ):
            logging.info(
                "迁移数据库：重建 ledgers 表，唯一约束改为 (owner_username, name)"
            )
            cursor.execute("PRAGMA foreign_keys = OFF")
            cursor.execute("""
                CREATE TABLE ledgers_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    description TEXT,
                    cost_method TEXT DEFAULT 'FIFO',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    owner_username TEXT DEFAULT '',
                    UNIQUE(owner_username, name)
                )
            """)
            cursor.execute("""
                INSERT INTO ledgers_new (id, name, description, cost_method, created_at, owner_username)
                SELECT id, name, description, COALESCE(cost_method,'FIFO'), created_at, COALESCE(owner_username,'')
                FROM ledgers
            """)
            cursor.execute("DROP TABLE ledgers")
            cursor.execute("ALTER TABLE ledgers_new RENAME TO ledgers")
            cursor.execute("PRAGMA foreign_keys = ON")

        # 检查是否存在 categories 表
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='categories'
        """)
        if not cursor.fetchone():
            logging.info("迁移数据库：创建 categories 表")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # 初始化默认投资类别（创建新表时直接插入，不需要 IGNORE）
            default_categories = [
                ("股票", "股票投资"),
                ("基金", "基金投资"),
                ("债券", "债券投资"),
                ("加密货币", "加密货币投资"),
                ("银行理财", "银行理财产品"),
                ("其他", "其他投资类型"),
            ]
            for cat_name, cat_desc in default_categories:
                cursor.execute(
                    """
                    INSERT INTO categories (name, description)
                    VALUES (?, ?)
                """,
                    (cat_name, cat_desc),
                )

        # 迁移 accounts 表：旧结构使用 currency(TEXT)，新结构使用 currency_id
        cursor.execute("PRAGMA table_info(accounts)")
        acc_cols = [c[1] for c in cursor.fetchall()]
        if "currency_id" not in acc_cols and "currency" in acc_cols:
            logging.info("迁移数据库：accounts 表从 currency(TEXT) 迁移到 currency_id")
            cursor.execute("PRAGMA foreign_keys = OFF")
            cursor.execute("""
                CREATE TABLE accounts_new (
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
                )
            """)
            cursor.execute("""
                INSERT INTO accounts_new (id, ledger_id, name, type, currency_id, description, created_at)
                SELECT a.id, a.ledger_id, a.name, a.type,
                       COALESCE(c.id, (SELECT id FROM currencies WHERE code = 'CNY' LIMIT 1)),
                       a.description, COALESCE(a.created_at, CURRENT_TIMESTAMP)
                FROM accounts a
                LEFT JOIN currencies c ON c.code = COALESCE(a.currency, 'CNY')
            """)
            cursor.execute("DROP TABLE accounts")
            cursor.execute("ALTER TABLE accounts_new RENAME TO accounts")
            cursor.execute("PRAGMA foreign_keys = ON")

        # 检查是否存在 fund_transaction_entries 表
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='fund_transaction_entries'
        """)
        if not cursor.fetchone():
            logging.info("迁移数据库：创建 fund_transaction_entries 表")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS fund_transaction_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fund_transaction_id INTEGER NOT NULL,
                    account_id INTEGER NOT NULL,
                    side TEXT NOT NULL CHECK(side IN ('debit', 'credit')),
                    amount REAL NOT NULL,
                    amount_cny REAL NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (fund_transaction_id) REFERENCES fund_transactions(id) ON DELETE CASCADE,
                    FOREIGN KEY (account_id) REFERENCES accounts(id)
                )
            """)

        # 迁移旧数据：如果 fund_transactions 表有旧结构，迁移到新结构
        cursor.execute("PRAGMA table_info(fund_transactions)")
        old_columns = [col[1] for col in cursor.fetchall()]

        # 如果存在旧字段（account_id, debit_account等），需要重建表
        if "account_id" in old_columns or "debit_account" in old_columns:
            logging.info("迁移数据库：检测到旧格式的 fund_transactions 表，开始迁移...")

            # 检查是否已经迁移过（通过检查是否有新表的数据）
            cursor.execute("SELECT COUNT(*) FROM fund_transaction_entries")
            result = cursor.fetchone()
            entry_count = result[0] if result else 0

            # 如果还没有迁移数据，先迁移数据
            if entry_count == 0 and "debit_account" in old_columns:
                logging.info("迁移数据库：迁移旧格式的 fund_transactions 数据")
                # 获取所有旧格式的记录
                cursor.execute("""
                    SELECT id, ledger_id, account_id, date, type, debit_account, credit_account,
                           amount, currency, amount_cny, target_account_id, notes
                    FROM fund_transactions
                    WHERE debit_account IS NOT NULL OR credit_account IS NOT NULL
                """)
                old_records = cursor.fetchall()

                for old_record in old_records:
                    (
                        old_id,
                        ledger_id,
                        account_id,
                        date,
                        type,
                        debit_account,
                        credit_account,
                        amount,
                        currency,
                        amount_cny,
                        target_account_id,
                        notes,
                    ) = old_record

                    # 如果金额为0，跳过
                    if not amount or amount == 0:
                        continue

                    # 创建借贷分录
                    if debit_account and account_id:
                        cursor.execute(
                            """
                            INSERT INTO fund_transaction_entries 
                            (fund_transaction_id, account_id, side, amount, amount_cny)
                            VALUES (?, ?, 'debit', ?, ?)
                        """,
                            (old_id, account_id, amount, amount_cny),
                        )

                    if credit_account:
                        credit_account_id = (
                            target_account_id if target_account_id else account_id
                        )
                        cursor.execute(
                            """
                            INSERT INTO fund_transaction_entries 
                            (fund_transaction_id, account_id, side, amount, amount_cny)
                            VALUES (?, ?, 'credit', ?, ?)
                        """,
                            (old_id, credit_account_id, amount, amount_cny),
                        )

            # 重建表结构
            logging.info("迁移数据库：重建 fund_transactions 表结构")
            # 禁用外键检查（临时）
            cursor.execute("PRAGMA foreign_keys = OFF")

            # 创建新表（使用 currency_id 外键）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS fund_transactions_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ledger_id INTEGER NOT NULL,
                    date TEXT NOT NULL,
                    type TEXT NOT NULL,
                    currency_id INTEGER NOT NULL,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (ledger_id) REFERENCES ledgers(id),
                    FOREIGN KEY (currency_id) REFERENCES currencies(id)
                )
            """)

            # 迁移数据：旧表为 currency(TEXT) 时通过 JOIN 得到 currency_id
            cursor.execute("PRAGMA table_info(fund_transactions)")
            ft_cols = [col[1] for col in cursor.fetchall()]
            if "currency_id" in ft_cols:
                cursor.execute("""
                    INSERT INTO fund_transactions_new (id, ledger_id, date, type, currency_id, notes, created_at)
                    SELECT id, ledger_id, date, type, currency_id, notes,
                           COALESCE(created_at, CURRENT_TIMESTAMP)
                    FROM fund_transactions
                """)
            else:
                cursor.execute("""
                    INSERT INTO fund_transactions_new (id, ledger_id, date, type, currency_id, notes, created_at)
                    SELECT ft.id, ft.ledger_id, ft.date, ft.type,
                           COALESCE(c.id, (SELECT id FROM currencies WHERE code = 'CNY' LIMIT 1)),
                           ft.notes, COALESCE(ft.created_at, CURRENT_TIMESTAMP)
                    FROM fund_transactions ft
                    LEFT JOIN currencies c ON c.code = ft.currency
                """)

            # 删除旧表
            cursor.execute("DROP TABLE fund_transactions")

            # 重命名新表
            cursor.execute(
                "ALTER TABLE fund_transactions_new RENAME TO fund_transactions"
            )

            # 重新启用外键检查
            cursor.execute("PRAGMA foreign_keys = ON")

            logging.info("迁移数据库：fund_transactions 表结构迁移完成")

        # 为 fund_transaction_entries 增加 currency_id（每笔分录可独立币种，支持人民币借、港币贷等）
        cursor.execute("PRAGMA table_info(fund_transaction_entries)")
        fte_columns = [col[1] for col in cursor.fetchall()]
        if "currency_id" not in fte_columns:
            logging.info("迁移数据库：为 fund_transaction_entries 添加 currency_id 列")
            cursor.execute(
                "ALTER TABLE fund_transaction_entries ADD COLUMN currency_id INTEGER REFERENCES currencies(id)"
            )
            cursor.execute("""
                UPDATE fund_transaction_entries
                SET currency_id = (SELECT currency_id FROM fund_transactions WHERE id = fund_transaction_entries.fund_transaction_id)
                WHERE currency_id IS NULL
            """)
            cursor.execute(
                "UPDATE fund_transaction_entries SET currency_id = (SELECT id FROM currencies WHERE code = 'CNY' LIMIT 1) WHERE currency_id IS NULL"
            )

        # 为 fund_transaction_entries 增加 subject_type（现金/持仓）列，用于开仓平仓的借贷区分
        cursor.execute("PRAGMA table_info(fund_transaction_entries)")
        fte_columns = [col[1] for col in cursor.fetchall()]
        if "subject_type" not in fte_columns:
            logging.info("迁移数据库：为 fund_transaction_entries 添加 subject_type 列")
            cursor.execute(
                "ALTER TABLE fund_transaction_entries ADD COLUMN subject_type TEXT DEFAULT 'cash'"
            )
            cursor.execute(
                "UPDATE fund_transaction_entries SET subject_type = 'cash' WHERE subject_type IS NULL"
            )

        # 回填历史开仓/平仓分录的 subject_type（旧数据迁移时会统一补为 cash）
        # 规则：
        # - 开仓：借=持仓(position)，贷=现金(cash)
        # - 平仓：借=现金(cash)，贷=持仓(position)
        cursor.execute("""
            UPDATE fund_transaction_entries
            SET subject_type = CASE
                WHEN (SELECT type FROM fund_transactions WHERE id = fund_transaction_id) = '开仓'
                     AND side = 'debit' THEN 'position'
                WHEN (SELECT type FROM fund_transactions WHERE id = fund_transaction_id) = '开仓'
                     AND side = 'credit' THEN 'cash'
                WHEN (SELECT type FROM fund_transactions WHERE id = fund_transaction_id) = '平仓'
                     AND side = 'debit' THEN 'cash'
                WHEN (SELECT type FROM fund_transactions WHERE id = fund_transaction_id) = '平仓'
                     AND side = 'credit' THEN 'position'
                ELSE subject_type
            END
            WHERE fund_transaction_id IN (
                SELECT id FROM fund_transactions WHERE type IN ('开仓', '平仓')
            )
        """)

        # 为 fund_transactions 添加 transaction_id，关联开仓/平仓产生的交易记录
        # 用于删除时级联：删交易记录则删资金明细，删资金明细则删交易记录
        cursor.execute("PRAGMA table_info(fund_transactions)")
        ft_columns = [col[1] for col in cursor.fetchall()]
        if "transaction_id" not in ft_columns:
            logging.info(
                "迁移数据库：为 fund_transactions 添加 transaction_id 列（关联交易记录）"
            )
            cursor.execute(
                "ALTER TABLE fund_transactions ADD COLUMN transaction_id INTEGER REFERENCES transactions(id)"
            )

        # 历史价格与历史快照表（用于历史价格功能）
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='security_price_history'
        """)
        if not cursor.fetchone():
            logging.info("迁移数据库：创建 security_price_history 表（证券历史收盘价）")
            cursor.execute("""
                CREATE TABLE security_price_history (
                    date TEXT NOT NULL,
                    code TEXT NOT NULL,
                    price REAL NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (date, code)
                )
            """)
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='exchange_rate_history'
        """)
        if not cursor.fetchone():
            logging.info(
                "迁移数据库：创建 exchange_rate_history 表（外汇历史汇率，相对人民币）"
            )
            cursor.execute("""
                CREATE TABLE exchange_rate_history (
                    date TEXT NOT NULL,
                    currency_code TEXT NOT NULL,
                    rate REAL NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (date, currency_code)
                )
            """)
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='position_history'
        """)
        if not cursor.fetchone():
            logging.info("迁移数据库：创建 position_history 表（历史持仓快照）")
            cursor.execute("""
                CREATE TABLE position_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    ledger_id INTEGER NOT NULL,
                    account_id INTEGER NOT NULL,
                    code TEXT NOT NULL,
                    name TEXT NOT NULL,
                    category_id INTEGER NOT NULL,
                    currency_id INTEGER NOT NULL,
                    quantity REAL NOT NULL,
                    avg_cost REAL NOT NULL,
                    price_at_date REAL NOT NULL,
                    market_value_local REAL NOT NULL,
                    rate_at_date REAL NOT NULL,
                    market_value_cny REAL NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (ledger_id) REFERENCES ledgers(id),
                    FOREIGN KEY (account_id) REFERENCES accounts(id),
                    FOREIGN KEY (category_id) REFERENCES categories(id),
                    FOREIGN KEY (currency_id) REFERENCES currencies(id)
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_position_history_date_ledger_account
                ON position_history(date, ledger_id, account_id)
            """)
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='return_rate'
        """)
        if not cursor.fetchone():
            logging.info("迁移数据库：创建 return_rate 表（收益率统计）")
            cursor.execute("""
                CREATE TABLE return_rate (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    ledger_id INTEGER NOT NULL,
                    发生金额 REAL,
                    确认份额 REAL,
                    确认净值 REAL,
                    总份额 REAL,
                    单位净值 REAL,
                    当日净资产 REAL,
                    当日损益 REAL,
                    当日收益率 TEXT,
                    累计收益率 REAL,
                    总资产 REAL,
                    账本 TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(date, ledger_id),
                    FOREIGN KEY (ledger_id) REFERENCES ledgers(id)
                )
            """)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_return_rate_date ON return_rate(date)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_return_rate_ledger ON return_rate(ledger_id)"
            )
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='rounding_diff'
        """)
        if not cursor.fetchone():
            logging.info("迁移数据库：创建 rounding_diff 表（尾差损益）")
            cursor.execute("""
                CREATE TABLE rounding_diff (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    ledger_id INTEGER NOT NULL,
                    原始份额 REAL,
                    确认份额 REAL,
                    尾差份额 REAL,
                    尾差金额 REAL,
                    确认净值 REAL,
                    账本 TEXT,
                    备注 TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(date, ledger_id),
                    FOREIGN KEY (ledger_id) REFERENCES ledgers(id)
                )
            """)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_rounding_diff_date ON rounding_diff(date)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_rounding_diff_ledger ON rounding_diff(ledger_id)"
            )
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='inventory_state'
        """)
        if not cursor.fetchone():
            logging.info("创建 inventory_state 表（库存计算状态，用于增量计算）")
            cursor.execute("""
                CREATE TABLE inventory_state (
                    ledger_id INTEGER PRIMARY KEY,
                    last_transaction_id INTEGER NOT NULL DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='account_balance_history'
        """)
        if not cursor.fetchone():
            logging.info(
                "迁移数据库：创建 account_balance_history 表（历史账户余额人民币）"
            )
            cursor.execute("""
                CREATE TABLE account_balance_history (
                    date TEXT NOT NULL,
                    account_id INTEGER NOT NULL,
                    balance_cny REAL NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (date, account_id),
                    FOREIGN KEY (account_id) REFERENCES accounts(id)
                )
            """)

        # Cloudreve 网盘绑定表（每用户绑定自己的 Cloudreve 服务器）
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='cloudreve_bindings'
        """)
        if not cursor.fetchone():
            logging.info("迁移数据库：创建 cloudreve_bindings 表（Cloudreve 网盘绑定）")
            cursor.execute("""
                CREATE TABLE cloudreve_bindings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    cloudreve_url TEXT NOT NULL,
                    access_token TEXT NOT NULL,
                    refresh_token TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_cloudreve_bindings_username ON cloudreve_bindings(username)"
            )

    def _init_default_data(self):
        """初始化默认数据（仅在首次创建时），币种与汇率使用设置中的默认值"""
        cursor = self.conn.cursor()

        # 初始化默认币种（统一从 default_currencies 读取，支持 config 覆盖）
        for code, name, symbol, rate in get_all_default_currencies(self.config_path):
            cursor.execute(
                """
                INSERT OR IGNORE INTO currencies (code, name, symbol, exchange_rate)
                VALUES (?, ?, ?, ?)
            """,
                (code, name, symbol, rate),
            )

        # 初始化默认投资类别（仅在表为空时）
        cursor.execute("SELECT COUNT(*) FROM categories")
        category_count = cursor.fetchone()[0]
        if category_count == 0:
            # 只有在没有任何类别时才初始化默认类别
            default_categories = [
                ("股票", "股票投资"),
                ("基金", "基金投资"),
                ("债券", "债券投资"),
                ("加密货币", "加密货币投资"),
                ("银行理财", "银行理财产品"),
                ("其他", "其他投资类型"),
            ]
            for cat_name, cat_desc in default_categories:
                cursor.execute(
                    """
                    INSERT INTO categories (name, description)
                    VALUES (?, ?)
                """,
                    (cat_name, cat_desc),
                )

        # 多用户模式：不再创建全局默认账本，每位用户需在设置中创建自己的账本

        self.conn.commit()

    def ensure_currency_exists(self, code: str) -> None:
        """若该币种不存在则插入（使用设置中的默认汇率），SQLite 使用 INSERT OR IGNORE。"""
        if not (code and str(code).strip()):
            return
        code = str(code).strip().upper()
        cursor = self.conn.cursor()
        cursor.execute("SELECT id FROM currencies WHERE code = ? LIMIT 1", (code,))
        if cursor.fetchone():
            return
        name, symbol, rate = get_currency_info(code, self.config_path)
        cursor.execute(
            """
            INSERT OR IGNORE INTO currencies (code, name, symbol, exchange_rate)
            VALUES (?, ?, ?, ?)
        """,
            (code, name, symbol, rate),
        )
        self.conn.commit()

    def get_connection(self) -> sqlite3.Connection:
        """获取数据库连接

        Returns:
            sqlite3.Connection: 数据库连接对象
        """
        if self.conn is None:
            self._connect()
        return self.conn

    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()
            self.conn = None
