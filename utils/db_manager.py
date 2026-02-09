"""
数据库管理器 - 基础设施层
负责数据库连接、表结构创建和初始化
"""

import sqlite3
import logging
from typing import Optional

# 默认汇率（相对于人民币）
DEFAULT_EXCHANGE_RATES = {
    'CNY': 1.0,      # 人民币
    'HKD': 0.92,     # 港币
    'USD': 7.25,     # 美元
    'EUR': 7.85,     # 欧元
    'GBP': 9.15,     # 英镑
    'JPY': 0.048,    # 日元
}


class DBManager:
    """数据库管理器 - 负责数据库连接和表结构管理"""

    def __init__(self, db_path: str = "investment.db"):
        """初始化数据库连接"""
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        # 启用外键约束
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._create_tables()
        self._init_default_data()

    def _create_tables(self):
        """创建数据库表"""
        cursor = self.conn.cursor()

        # 账本表（用户/家庭成员）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ledgers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                cost_method TEXT DEFAULT 'FIFO',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 账户表（银行、券商等）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ledger_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                currency TEXT DEFAULT 'CNY',
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ledger_id) REFERENCES ledgers(id),
                UNIQUE(ledger_id, name)
            )
        ''')

        # 币种表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS currencies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                symbol TEXT NOT NULL,
                exchange_rate REAL NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 投资类别表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 交易记录表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ledger_id INTEGER NOT NULL,
                account_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                type TEXT NOT NULL,
                category TEXT NOT NULL,
                code TEXT NOT NULL,
                name TEXT NOT NULL,
                quantity REAL NOT NULL,
                price REAL NOT NULL,
                currency TEXT DEFAULT 'CNY',
                amount REAL NOT NULL,
                amount_cny REAL NOT NULL,
                fee REAL DEFAULT 0,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ledger_id) REFERENCES ledgers(id),
                FOREIGN KEY (account_id) REFERENCES accounts(id)
            )
        ''')

        # 资金明细表（借贷记账法）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS fund_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ledger_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                type TEXT NOT NULL,
                currency TEXT DEFAULT 'CNY',
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ledger_id) REFERENCES ledgers(id)
            )
        ''')

        # 借贷分录明细表（支持多借多贷）
        cursor.execute('''
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
        ''')

        # 持仓表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ledger_id INTEGER NOT NULL,
                account_id INTEGER NOT NULL,
                code TEXT NOT NULL,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                currency TEXT DEFAULT 'CNY',
                quantity REAL NOT NULL,
                avg_cost REAL NOT NULL,
                current_price REAL NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ledger_id) REFERENCES ledgers(id),
                FOREIGN KEY (account_id) REFERENCES accounts(id),
                UNIQUE(ledger_id, account_id, code)
            )
        ''')

        # 数据库迁移：检查并添加缺失的列
        self._migrate_database(cursor)

        self.conn.commit()

    def _migrate_database(self, cursor):
        """数据库迁移：检查并添加缺失的列和表"""
        # 检查 ledgers 表是否有 cost_method 列
        cursor.execute("PRAGMA table_info(ledgers)")
        columns = [col[1] for col in cursor.fetchall()]

        if 'cost_method' not in columns:
            logging.info("迁移数据库：为 ledgers 表添加 cost_method 列")
            cursor.execute("ALTER TABLE ledgers ADD COLUMN cost_method TEXT DEFAULT 'FIFO'")

        # 检查是否存在 categories 表
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='categories'
        """)
        if not cursor.fetchone():
            logging.info("迁移数据库：创建 categories 表")
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            # 初始化默认投资类别（创建新表时直接插入，不需要 IGNORE）
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
                    VALUES (?, ?)
                ''', (cat_name, cat_desc))

        # 检查是否存在 fund_transaction_entries 表
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='fund_transaction_entries'
        """)
        if not cursor.fetchone():
            logging.info("迁移数据库：创建 fund_transaction_entries 表")
            cursor.execute('''
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
            ''')

        # 迁移旧数据：如果 fund_transactions 表有旧结构，迁移到新结构
        cursor.execute("PRAGMA table_info(fund_transactions)")
        old_columns = [col[1] for col in cursor.fetchall()]
        
        # 如果存在旧字段（account_id, debit_account等），需要重建表
        if 'account_id' in old_columns or 'debit_account' in old_columns:
            logging.info("迁移数据库：检测到旧格式的 fund_transactions 表，开始迁移...")
            
            # 检查是否已经迁移过（通过检查是否有新表的数据）
            cursor.execute("SELECT COUNT(*) FROM fund_transaction_entries")
            result = cursor.fetchone()
            entry_count = result[0] if result else 0
            
            # 如果还没有迁移数据，先迁移数据
            if entry_count == 0 and 'debit_account' in old_columns:
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
                    (old_id, ledger_id, account_id, date, type, debit_account, 
                     credit_account, amount, currency, amount_cny, target_account_id, notes) = old_record
                    
                    # 如果金额为0，跳过
                    if not amount or amount == 0:
                        continue
                    
                    # 创建借贷分录
                    if debit_account and account_id:
                        cursor.execute("""
                            INSERT INTO fund_transaction_entries 
                            (fund_transaction_id, account_id, side, amount, amount_cny)
                            VALUES (?, ?, 'debit', ?, ?)
                        """, (old_id, account_id, amount, amount_cny))
                    
                    if credit_account:
                        credit_account_id = target_account_id if target_account_id else account_id
                        cursor.execute("""
                            INSERT INTO fund_transaction_entries 
                            (fund_transaction_id, account_id, side, amount, amount_cny)
                            VALUES (?, ?, 'credit', ?, ?)
                        """, (old_id, credit_account_id, amount, amount_cny))
            
            # 重建表结构
            logging.info("迁移数据库：重建 fund_transactions 表结构")
            # 禁用外键检查（临时）
            cursor.execute("PRAGMA foreign_keys = OFF")
            
            # 创建新表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS fund_transactions_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ledger_id INTEGER NOT NULL,
                    date TEXT NOT NULL,
                    type TEXT NOT NULL,
                    currency TEXT DEFAULT 'CNY',
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (ledger_id) REFERENCES ledgers(id)
                )
            ''')
            
            # 迁移数据（只迁移基本字段）
            cursor.execute("""
                INSERT INTO fund_transactions_new (id, ledger_id, date, type, currency, notes, created_at)
                SELECT id, ledger_id, date, type, 
                       COALESCE(currency, 'CNY') as currency, 
                       notes, 
                       COALESCE(created_at, CURRENT_TIMESTAMP) as created_at
                FROM fund_transactions
            """)
            
            # 删除旧表
            cursor.execute("DROP TABLE fund_transactions")
            
            # 重命名新表
            cursor.execute("ALTER TABLE fund_transactions_new RENAME TO fund_transactions")
            
            # 重新启用外键检查
            cursor.execute("PRAGMA foreign_keys = ON")
            
            logging.info("迁移数据库：fund_transactions 表结构迁移完成")

        # 为 fund_transaction_entries 增加 subject_type（现金/持仓）列，用于开仓平仓的借贷区分
        cursor.execute("PRAGMA table_info(fund_transaction_entries)")
        fte_columns = [col[1] for col in cursor.fetchall()]
        if 'subject_type' not in fte_columns:
            logging.info("迁移数据库：为 fund_transaction_entries 添加 subject_type 列")
            cursor.execute(
                "ALTER TABLE fund_transaction_entries ADD COLUMN subject_type TEXT DEFAULT 'cash'"
            )
            cursor.execute(
                "UPDATE fund_transaction_entries SET subject_type = 'cash' WHERE subject_type IS NULL"
            )

        # 回填历史开仓/平仓分录的 subject_type（旧数据迁移时会统一补为 cash）
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

    def _init_default_data(self):
        """初始化默认数据（仅在首次创建时）"""
        cursor = self.conn.cursor()

        # 初始化默认币种
        for code, rate in DEFAULT_EXCHANGE_RATES.items():
            currency_info = {
                'CNY': ('人民币', '¥'),
                'HKD': ('港币', 'HK$'),
                'USD': ('美元', '$'),
                'EUR': ('欧元', '€'),
                'GBP': ('英镑', '£'),
                'JPY': ('日元', '¥'),
            }
            name, symbol = currency_info.get(code, (code, code))
            cursor.execute('''
                INSERT OR IGNORE INTO currencies (code, name, symbol, exchange_rate)
                VALUES (?, ?, ?, ?)
            ''', (code, name, symbol, rate))

        # 初始化默认投资类别（仅在表为空时）
        cursor.execute('SELECT COUNT(*) FROM categories')
        category_count = cursor.fetchone()[0]
        if category_count == 0:
            # 只有在没有任何类别时才初始化默认类别
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
                    VALUES (?, ?)
                ''', (cat_name, cat_desc))

        # 初始化默认账本（仅在不存在时创建）
        cursor.execute('''
            INSERT OR IGNORE INTO ledgers (name, description)
            VALUES ('默认账本', '我的投资账本')
        ''')

        # 获取默认账本ID
        cursor.execute('SELECT id FROM ledgers WHERE name = ?', ('默认账本',))
        ledger = cursor.fetchone()
        if ledger:
            ledger_id = ledger[0]
            # 检查该账本下是否已有任何账户
            cursor.execute('SELECT COUNT(*) FROM accounts WHERE ledger_id = ?', (ledger_id,))
            account_count = cursor.fetchone()[0]
            
            # 只有在账本下没有任何账户时才创建默认账户（首次初始化）
            # 这样即使用户删除了默认账户或修改了名称，也不会重新创建
            if account_count == 0:
                default_accounts = [
                    ('默认账户', '其他', 'CNY', '默认投资账户'),
                ]
                for acc_name, acc_type, currency, desc in default_accounts:
                    cursor.execute('''
                        INSERT INTO accounts (ledger_id, name, type, currency, description)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (ledger_id, acc_name, acc_type, currency, desc))

        self.conn.commit()

    def get_connection(self):
        """获取数据库连接"""
        return self.conn

    def close(self):
        """关闭数据库连接"""
        self.conn.close()
