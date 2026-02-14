"""
数据库模块 - 支持 SQLite / PostgreSQL 存储投资数据
支持多账户、多账本、多币种、多数据库

模块化架构：
- db_sqlite_manager.py / db_postgres_manager.py: 基础设施层（数据库连接、表结构）
- crud_transactions.py: 业务操作层（买入、卖出、分红的增删改查）
- analytics.py: 逻辑计算层（收益率、持仓成本、资产占比）
"""

import sqlite3
import pandas as pd
from typing import Optional, Dict, List
from datetime import datetime, timedelta
import logging

from utils.db_base import get_db_manager
from utils.db_config import get_database_config

# 多数据库：统一 IntegrityError 类型（SQLite 与 PostgreSQL）
try:
    import psycopg2

    _DB_INTEGRITY_ERROR = (sqlite3.IntegrityError, psycopg2.IntegrityError)
except ImportError:
    _DB_INTEGRITY_ERROR = (sqlite3.IntegrityError,)
from utils.get_market_price import (
    get_stock_close_price,
    get_Settlement_exchange_rate,
    get_stock_close_price_range,
    get_exchange_rate_range,
)
from utils.cache_utils import clear_related_cache
from crud_transactions import TransactionCRUD
from analytics import Analytics, COST_METHOD_FIFO, COST_METHOD_WAC, DEFAULT_COST_METHOD

# 默认汇率（相对于人民币）
DEFAULT_EXCHANGE_RATES = {
    "CNY": 1.0,  # 人民币
    "HKD": 0.92,  # 港币
    "USD": 7.25,  # 美元
    "EUR": 7.85,  # 欧元
    "GBP": 9.15,  # 英镑
    "JPY": 0.048,  # 日元
}


class Database:
    """投资数据库类 - 主入口，整合各个模块，支持 SQLite / PostgreSQL"""

    def __init__(
        self,
        db_path: Optional[str] = None,
        db_type: Optional[str] = None,
        config_path: Optional[str] = None,
        **db_kwargs,
    ):
        """
        初始化数据库连接

        Args:
            db_path: SQLite 数据库路径（仅当 db_type 为 sqlite 且未从 config 读取时使用）
            db_type: 数据库类型 'sqlite' | 'postgresql'，不传则从 config.yaml 读取
            config_path: config.yaml 路径，用于读取数据库配置
            **db_kwargs: 覆盖配置的数据库参数（如 pg_host, pg_port 等）
        """
        cfg = get_database_config(config_path)
        self.db_type = db_type or cfg["type"]
        self.db_path = db_path or cfg["sqlite"]["path"]

        # 初始化基础设施层（根据配置选择 SQLite、PostgreSQL 或 D1）
        self.db_manager = get_db_manager(
            db_type=self.db_type,
            db_path=self.db_path,
            config_path=config_path,
            pg_host=db_kwargs.get("pg_host") or cfg["postgresql"]["host"],
            pg_port=db_kwargs.get("pg_port") or cfg["postgresql"]["port"],
            pg_database=db_kwargs.get("pg_database") or cfg["postgresql"]["database"],
            pg_user=db_kwargs.get("pg_user") or cfg["postgresql"]["user"],
            pg_password=db_kwargs.get("pg_password") or cfg["postgresql"]["password"],
            pg_sslmode=db_kwargs.get("pg_sslmode") or cfg["postgresql"]["sslmode"],
            d1_account_id=db_kwargs.get("d1_account_id") or cfg["d1"]["account_id"],
            d1_database_id=db_kwargs.get("d1_database_id") or cfg["d1"]["database_id"],
            d1_api_token=db_kwargs.get("d1_api_token") or cfg["d1"]["api_token"],
        )
        self.conn = self.db_manager.get_connection()

        # 初始化业务操作层
        self.transaction_crud = TransactionCRUD(self.db_manager)

        # 初始化逻辑计算层
        self.analytics = Analytics(self.db_manager)

        # 保持向后兼容：暴露库存管理器
        self.fifo_inventory = self.analytics.fifo_inventory
        self.wac_inventory = self.analytics.wac_inventory
        self._ledger_cost_methods = self.analytics._ledger_cost_methods

    # ============ 账本管理 ============

    def get_ledgers(self, username: Optional[str] = None) -> pd.DataFrame:
        """获取账本列表。若传入 username 则仅返回该用户拥有的账本（多用户数据隔离）。"""
        if username is not None:
            query = "SELECT * FROM ledgers WHERE owner_username = ? ORDER BY id"
            return pd.read_sql_query(query, self.conn, params=[username])
        query = "SELECT * FROM ledgers ORDER BY id"
        return pd.read_sql_query(query, self.conn)

    def add_ledger(
        self,
        name: str,
        description: str = "",
        cost_method: str = DEFAULT_COST_METHOD,
        owner_username: Optional[str] = None,
    ) -> bool:
        """添加账本

        Args:
            name: 账本名称
            description: 账本描述
            cost_method: 成本计算方法，FIFO 或 WAC
            owner_username: 所属用户名（多用户隔离），不传则为空
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                INSERT INTO ledgers (name, description, cost_method, owner_username)
                VALUES (?, ?, ?, ?)
            """,
                (name, description, cost_method, owner_username or ""),
            )
            self.conn.commit()

            # 更新缓存
            ledger_id = cursor.lastrowid
            self.analytics._ledger_cost_methods[ledger_id] = cost_method

            # 清除相关缓存
            clear_related_cache()

            return True
        except Exception as e:
            logging.error(f"添加账本失败: {e}")
            return False

    def update_ledger(
        self,
        ledger_id: int,
        name: str,
        description: str,
        cost_method: str,
        owner_username: Optional[str] = None,
    ) -> bool:
        """更新账本信息。若传入 owner_username 则仅允许更新该用户拥有的账本。"""
        try:
            ledger_id = int(ledger_id)
            old_cost_method = self.analytics.get_ledger_cost_method(ledger_id)
            cursor = self.conn.cursor()
            if owner_username is not None:
                cursor.execute(
                    """
                    UPDATE ledgers
                    SET name = ?, description = ?, cost_method = ?
                    WHERE id = ? AND owner_username = ?
                """,
                    (name, description, cost_method, ledger_id, owner_username),
                )
            else:
                cursor.execute(
                    """
                    UPDATE ledgers
                    SET name = ?, description = ?, cost_method = ?
                    WHERE id = ?
                """,
                    (name, description, cost_method, ledger_id),
                )
            self.conn.commit()
            if cursor.rowcount == 0:
                return False

            # 如果成本方法改变，需要重建库存
            if old_cost_method != cost_method:
                self.analytics._ledger_cost_methods[ledger_id] = cost_method
                self.analytics._rebuild_all_inventory()

            # 清除相关缓存
            clear_related_cache(ledger_id=ledger_id)

            return True
        except Exception as e:
            logging.error(f"更新账本失败: {e}")
            return False

    def delete_ledger(
        self, ledger_id: int, owner_username: Optional[str] = None
    ) -> bool:
        """删除账本。若传入 owner_username 则仅允许删除该用户拥有的账本。"""
        try:
            ledger_id = int(ledger_id)
            cursor = self.conn.cursor()
            if owner_username is not None:
                cursor.execute(
                    "SELECT id FROM ledgers WHERE id = ? AND owner_username = ?",
                    (ledger_id, owner_username),
                )
                if not cursor.fetchone():
                    return False
            cursor.execute("DELETE FROM positions WHERE ledger_id = ?", (ledger_id,))
            cursor.execute("DELETE FROM transactions WHERE ledger_id = ?", (ledger_id,))
            cursor.execute("DELETE FROM accounts WHERE ledger_id = ?", (ledger_id,))
            if owner_username is not None:
                cursor.execute(
                    "DELETE FROM ledgers WHERE id = ? AND owner_username = ?",
                    (ledger_id, owner_username),
                )
            else:
                cursor.execute("DELETE FROM ledgers WHERE id = ?", (ledger_id,))
            deleted = cursor.rowcount
            self.conn.commit()
            if owner_username is not None and deleted == 0:
                return False

            # 清除相关缓存
            clear_related_cache(ledger_id=ledger_id)

            return True
        except Exception as e:
            logging.error(f"删除账本失败: {e}")
            return False

    def get_ledger_cost_method(self, ledger_id: int) -> str:
        """获取账本的成本计算方法"""
        return self.analytics.get_ledger_cost_method(ledger_id)

    def update_ledger_cost_method(self, ledger_id: int, cost_method: str) -> bool:
        """更新账本的成本计算方法"""
        if cost_method not in [COST_METHOD_FIFO, COST_METHOD_WAC]:
            logging.error(f"无效的成本计算方法: {cost_method}")
            return False

        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                UPDATE ledgers
                SET cost_method = ?
                WHERE id = ?
            """,
                (cost_method, ledger_id),
            )
            self.conn.commit()

            # 更新缓存
            self.analytics._ledger_cost_methods[ledger_id] = cost_method

            # 重建库存以应用新的成本计算方法
            self.analytics._rebuild_all_inventory()

            # 清除相关缓存
            clear_related_cache(ledger_id=ledger_id)

            logging.info(f"账本 {ledger_id} 的成本计算方法已更新为 {cost_method}")
            return True
        except Exception as e:
            logging.error(f"更新成本计算方法失败: {e}")
            return False

    # ============ 账户管理 ============

    def get_accounts(self, ledger_id: Optional[int] = None) -> pd.DataFrame:
        """获取账户列表（accounts 表使用 currency_id 外键，通过 JOIN 得到 c.code 作为 currency）"""
        if ledger_id:
            query = """
                SELECT a.*, l.name as ledger_name, c.code as currency, c.name as currency_name, c.symbol as currency_symbol
                FROM accounts a
                LEFT JOIN ledgers l ON a.ledger_id = l.id
                LEFT JOIN currencies c ON a.currency_id = c.id
                WHERE a.ledger_id = ?
                ORDER BY a.id
            """
            return pd.read_sql_query(query, self.conn, params=[ledger_id])
        else:
            query = """
                SELECT a.*, l.name as ledger_name, c.code as currency, c.name as currency_name, c.symbol as currency_symbol
                FROM accounts a
                LEFT JOIN ledgers l ON a.ledger_id = l.id
                LEFT JOIN currencies c ON a.currency_id = c.id
                ORDER BY a.ledger_id, a.id
            """
            return pd.read_sql_query(query, self.conn)

    def add_account(
        self,
        ledger_id: int,
        name: str,
        acc_type: str,
        currency: str = "CNY",
        description: str = "",
    ) -> bool:
        """添加账户（currency 为币种代码，如 'CNY'）"""
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT id FROM currencies WHERE code = ?", (currency,))
            row = cursor.fetchone()
            currency_id = row[0] if row else None
            if currency_id is None:
                # 尝试插入默认币种
                rate = DEFAULT_EXCHANGE_RATES.get(currency, 1.0)
                info = {"CNY": ("人民币", "¥"), "HKD": ("港币", "HK$"), "USD": ("美元", "$"),
                        "EUR": ("欧元", "€"), "GBP": ("英镑", "£"), "JPY": ("日元", "¥")}
                name_str, symbol = info.get(currency, (currency, currency))
                cursor.execute(
                    "INSERT OR IGNORE INTO currencies (code, name, symbol, exchange_rate) VALUES (?, ?, ?, ?)",
                    (currency, name_str, symbol, rate),
                )
                self.conn.commit()
                cursor.execute("SELECT id FROM currencies WHERE code = ?", (currency,))
                row = cursor.fetchone()
                currency_id = row[0] if row else None
            if currency_id is None:
                logging.warning(f"币种 '{currency}' 不存在，添加账户失败")
                return False
            cursor.execute(
                """
                INSERT INTO accounts (ledger_id, name, type, currency_id, description)
                VALUES (?, ?, ?, ?, ?)
            """,
                (ledger_id, name, acc_type, currency_id, description),
            )
            self.conn.commit()

            # 清除相关缓存
            clear_related_cache(ledger_id=ledger_id)

            return True
        except Exception as e:
            logging.error(f"添加账户失败: {e}")
            return False

    def update_account(
        self,
        account_id: int,
        name: str,
        acc_type: str,
        currency: Optional[str] = None,
        description: str = "",
    ) -> bool:
        """更新账户信息

        注意：
            - 若 currency 为空/None，则保留原有币种不变；
            - 若 currency 提供为币种代码（如 'CNY'），则会更新对应的 currency_id。
        """
        try:
            account_id = int(account_id)
            cursor = self.conn.cursor()

            # 先获取当前账户信息（包含原有币种）
            cursor.execute(
                "SELECT ledger_id, name, currency_id FROM accounts WHERE id = ?",
                (account_id,),
            )
            account_info = cursor.fetchone()
            if not account_info:
                logging.warning(f"账户 {account_id} 不存在")
                return False

            ledger_id, old_name, old_currency_id = account_info

            # 如果名称改变，检查新名称是否与同一账本下的其他账户冲突
            if name != old_name:
                cursor.execute(
                    """
                    SELECT id FROM accounts 
                    WHERE ledger_id = ? AND name = ? AND id != ?
                """,
                    (ledger_id, name, account_id),
                )
                if cursor.fetchone():
                    logging.error(f"账户名称 '{name}' 在同一账本下已存在")
                    return False

            # 解析币种代码为 currency_id；若未提供则沿用旧值
            if currency is None or str(currency).strip() == "":
                currency_id = old_currency_id
            else:
                cursor.execute("SELECT id FROM currencies WHERE code = ?", (currency,))
                curr_row = cursor.fetchone()
                currency_id = curr_row[0] if curr_row else None
                if currency_id is None:
                    logging.warning(f"币种 '{currency}' 不存在，更新账户失败")
                    return False

            # 执行更新
            cursor.execute(
                """
                UPDATE accounts
                SET name = ?, type = ?, currency_id = ?, description = ?
                WHERE id = ?
            """,
                (name, acc_type, currency_id, description, account_id),
            )

            if cursor.rowcount == 0:
                logging.warning(f"账户 {account_id} 更新失败，可能已被删除")
                return False

            self.conn.commit()

            # 清除相关缓存
            clear_related_cache(ledger_id=ledger_id, account_id=account_id)

            logging.info(f"成功更新账户 {account_id}: {old_name} -> {name}")
            return True
        except _DB_INTEGRITY_ERROR as e:
            logging.error(f"更新账户 {account_id} 时违反唯一约束: {e}")
            self.conn.rollback()
            return False
        except Exception as e:
            logging.error(f"更新账户 {account_id} 时发生错误: {e}", exc_info=True)
            self.conn.rollback()
            return False

    def get_account_related_counts(self, account_id: int) -> dict:
        """获取账户相关的明细数量"""
        try:
            account_id = int(account_id)
            cursor = self.conn.cursor()

            # 统计各种明细数量
            cursor.execute(
                "SELECT COUNT(*) FROM positions WHERE account_id = ?", (account_id,)
            )
            positions_count = cursor.fetchone()[0]

            cursor.execute(
                "SELECT COUNT(*) FROM transactions WHERE account_id = ?", (account_id,)
            )
            transactions_count = cursor.fetchone()[0]

            cursor.execute(
                "SELECT COUNT(*) FROM fund_transaction_entries WHERE account_id = ?",
                (account_id,),
            )
            fund_entries_count = cursor.fetchone()[0]

            return {
                "positions": positions_count,
                "transactions": transactions_count,
                "fund_entries": fund_entries_count,
                "total": positions_count + transactions_count + fund_entries_count,
            }
        except Exception as e:
            logging.error(f"获取账户相关数量失败: {e}")
            return {"positions": 0, "transactions": 0, "fund_entries": 0, "total": 0}

    def delete_account(self, account_id: int) -> bool:
        """删除账户及其所有相关明细"""
        try:
            account_id = int(account_id)
            cursor = self.conn.cursor()

            # 确保外键约束已启用
            cursor.execute("PRAGMA foreign_keys = ON")

            # 先检查账户是否存在
            cursor.execute("SELECT id FROM accounts WHERE id = ?", (account_id,))
            if not cursor.fetchone():
                logging.warning(f"账户 {account_id} 不存在")
                return False

            # 删除所有相关明细（按顺序删除，避免外键约束问题）
            deleted_positions = cursor.execute(
                "DELETE FROM positions WHERE account_id = ?", (account_id,)
            ).rowcount
            deleted_transactions = cursor.execute(
                "DELETE FROM transactions WHERE account_id = ?", (account_id,)
            ).rowcount
            deleted_fund_entries = cursor.execute(
                "DELETE FROM fund_transaction_entries WHERE account_id = ?",
                (account_id,),
            ).rowcount
            # 历史快照表也引用 account_id，必须一并删除（若表存在）
            for table in ("position_history", "account_balance_history"):
                try:
                    cursor.execute(
                        f"DELETE FROM {table} WHERE account_id = ?", (account_id,)
                    )
                except Exception as tbe:
                    if "no such table" not in str(tbe).lower() and "does not exist" not in str(tbe).lower():
                        raise

            # 最后删除账户本身
            deleted_accounts = cursor.execute(
                "DELETE FROM accounts WHERE id = ?", (account_id,)
            ).rowcount

            if deleted_accounts == 0:
                logging.warning(f"账户 {account_id} 删除失败，可能已被删除")
                self.conn.rollback()
                return False

            self.conn.commit()

            # 清除相关缓存
            clear_related_cache(account_id=account_id)

            logging.info(
                f"成功删除账户 {account_id}，同时删除了 {deleted_positions} 个持仓、{deleted_transactions} 个交易、{deleted_fund_entries} 个资金明细"
            )
            return True
        except _DB_INTEGRITY_ERROR as e:
            logging.error(f"外键约束错误，无法删除账户 {account_id}: {e}")
            self.conn.rollback()
            return False
        except Exception as e:
            logging.error(f"删除账户 {account_id} 时发生错误: {e}", exc_info=True)
            self.conn.rollback()
            return False

    # ============ 币种管理 ============

    def get_currencies(self) -> pd.DataFrame:
        """获取所有币种"""
        query = "SELECT * FROM currencies ORDER BY id"
        return pd.read_sql_query(query, self.conn)

    def update_exchange_rate(self, code: str, rate: float) -> bool:
        """更新汇率（如果汇率有变化，会自动触发历史数据修正）"""
        try:
            cursor = self.conn.cursor()

            old_rate = None
            cursor.execute(
                "SELECT exchange_rate FROM currencies WHERE code = ?", (code,)
            )
            row = cursor.fetchone()
            if row:
                old_rate = float(row[0])
                if old_rate is not None and abs(old_rate - rate) < 0.0001:
                    logging.info(f"汇率 {code} 未变化（{old_rate}），跳过更新")
                    return True

            cursor.execute(
                """
                UPDATE currencies
                SET exchange_rate = ?, updated_at = CURRENT_TIMESTAMP
                WHERE code = ?
            """,
                (rate, code),
            )
            self.conn.commit()

            clear_related_cache()

            if old_rate is not None:
                logging.info(
                    f"汇率 {code} 已更新：{old_rate} → {rate}，触发历史数据修正"
                )
                self._trigger_history_recalc_for_rate_change(code, rate)
            else:
                logging.info(f"汇率 {code} 已设置为 {rate}")

            return True
        except Exception as e:
            logging.error(f"更新汇率失败: {e}")
            return False

    def _trigger_history_recalc_for_rate_change(
        self, currency_code: str, new_rate: float
    ) -> None:
        """当汇率变化时，触发相关历史数据的重新计算

        Args:
            currency_code: 币种代码
            new_rate: 新的汇率
        """
        from datetime import datetime, timedelta

        try:
            cursor = self.conn.cursor()

            cursor.execute(
                """
                SELECT MIN(date) FROM fund_transactions
                WHERE currency_id = (SELECT id FROM currencies WHERE code = ?)
            """,
                (currency_code,),
            )
            row = cursor.fetchone()
            if not row or not row[0]:
                logging.info(f"币种 {currency_code} 没有交易记录，无需修正历史数据")
                return

            first_date = str(row[0])
            yesterday = datetime.now() - timedelta(days=1)
            end_date = yesterday.strftime("%Y-%m-%d")

            if first_date > end_date:
                return

            logging.info(
                f"正在修正币种 {currency_code} 从 {first_date} 到 {end_date} 的历史数据..."
            )

            self.recalculate_transaction_rates(first_date, end_date)
            self.save_position_and_balance_history_range(first_date, end_date)
            self.generate_return_rate(full_refresh=True, write_to_db=True)

            logging.info(f"币种 {currency_code} 的历史数据修正完成")
        except Exception as e:
            logging.error(f"修正历史数据失败: {e}")

    def add_currency(self, code: str, name: str, symbol: str, rate: float) -> bool:
        """添加币种"""
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                INSERT INTO currencies (code, name, symbol, exchange_rate)
                VALUES (?, ?, ?, ?)
            """,
                (code, name, symbol, rate),
            )
            self.conn.commit()

            # 清除相关缓存
            clear_related_cache()

            return True
        except Exception as e:
            logging.error(f"添加币种失败: {e}")
            return False

    def get_exchange_rate(self, currency: str) -> float:
        """获取汇率"""
        return self.analytics.get_exchange_rate(currency)

    def convert_to_cny(self, amount: float, currency: str) -> float:
        """转换为人民币（使用当前汇率）"""
        return self.analytics.convert_to_cny(amount, currency)

    def convert_to_cny_at_date(self, amount: float, currency: str, date: str) -> float:
        """按指定日期的汇率转换为人民币，若无历史汇率则回退到当前汇率"""
        return self.analytics.convert_to_cny_at_date(amount, currency, date)

    def get_exchange_rates_at_date(self, date: str) -> Dict[str, float]:
        """获取指定日期各币种对人民币的汇率，供前端试算与自动平衡使用。"""
        codes = ["CNY", "USD", "HKD", "EUR"]
        return {c: self._get_rate_at_date(c, date) for c in codes}

    # ============ 投资类别管理 ============

    def get_categories(self) -> pd.DataFrame:
        """获取所有投资类别"""
        query = "SELECT * FROM categories ORDER BY id"
        return pd.read_sql_query(query, self.conn)

    def add_category(self, name: str, description: str = None) -> bool:
        """添加投资类别"""
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                INSERT INTO categories (name, description)
                VALUES (?, ?)
            """,
                (name, description),
            )
            self.conn.commit()

            # 清除相关缓存
            clear_related_cache()

            return True
        except _DB_INTEGRITY_ERROR:
            # 名称已存在
            return False
        except Exception as e:
            logging.error(f"添加类别失败: {e}")
            return False

    def update_category(
        self, category_id: int, name: str, description: str = None
    ) -> bool:
        """更新投资类别"""
        try:
            cursor = self.conn.cursor()

            # 先获取当前类别的名称
            cursor.execute("SELECT name FROM categories WHERE id = ?", (category_id,))
            result = cursor.fetchone()
            if not result:
                return False  # 类别不存在

            current_name = result[0]

            # 如果名称改变了，检查新名称是否与其他类别冲突
            if name != current_name:
                cursor.execute(
                    "SELECT id FROM categories WHERE name = ? AND id != ?",
                    (name, category_id),
                )
                if cursor.fetchone():
                    return False  # 名称已存在

            # 执行更新
            cursor.execute(
                """
                UPDATE categories
                SET name = ?, description = ?
                WHERE id = ?
            """,
                (name, description, category_id),
            )

            # 检查是否有行被更新
            if cursor.rowcount == 0:
                return False

            self.conn.commit()

            # 清除相关缓存
            clear_related_cache()

            return True
        except Exception as e:
            logging.error(f"更新类别失败: {e}")
            self.conn.rollback()
            return False

    def delete_category(self, category_id: int) -> bool:
        """删除投资类别"""
        try:
            cursor = self.conn.cursor()

            # 先检查类别是否存在
            cursor.execute("SELECT name FROM categories WHERE id = ?", (category_id,))
            result = cursor.fetchone()
            if not result:
                logging.warning(f"类别 {category_id} 不存在")
                return False

            category_name = result[0]

            # 检查是否有交易记录使用该类别
            cursor.execute(
                "SELECT COUNT(*) FROM transactions WHERE category_id = ?",
                (category_id,),
            )
            transaction_count = cursor.fetchone()[0]

            # 检查是否有持仓记录使用该类别
            cursor.execute(
                "SELECT COUNT(*) FROM positions WHERE category_id = ?", (category_id,)
            )
            position_count = cursor.fetchone()[0]

            if transaction_count > 0 or position_count > 0:
                # 有相关数据，不允许删除
                logging.info(
                    f"无法删除类别 '{category_name}'，存在 {transaction_count} 条交易记录和 {position_count} 条持仓记录"
                )
                return False

            # 执行删除
            cursor.execute("DELETE FROM categories WHERE id = ?", (category_id,))

            # 检查是否有行被删除
            if cursor.rowcount == 0:
                logging.warning(f"删除类别 {category_id} 失败，没有行被删除")
                return False

            self.conn.commit()

            # 清除相关缓存
            clear_related_cache()

            logging.info(f"成功删除类别 '{category_name}' (ID: {category_id})")
            return True
        except Exception as e:
            logging.error(f"删除类别时发生错误: {e}")
            self.conn.rollback()
            return False

    def get_category_usage_count(self, category_id: int) -> Dict[str, int]:
        """获取投资类别的使用情况"""
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT id FROM categories WHERE id = ?", (category_id,))
            if not cursor.fetchone():
                return {"transactions": 0, "positions": 0}

            # 统计交易记录数
            cursor.execute(
                "SELECT COUNT(*) FROM transactions WHERE category_id = ?",
                (category_id,),
            )
            transaction_count = cursor.fetchone()[0]

            # 统计持仓记录数
            cursor.execute(
                "SELECT COUNT(*) FROM positions WHERE category_id = ?", (category_id,)
            )
            position_count = cursor.fetchone()[0]

            return {"transactions": transaction_count, "positions": position_count}
        except Exception as e:
            logging.error(f"获取类别使用情况失败: {e}")
            return {"transactions": 0, "positions": 0}

    # ============ 交易管理 ============

    def _update_history_for_date(
        self,
        start_date: str,
        ledger_id: Optional[int] = None,
        account_id: Optional[int] = None,
    ) -> None:
        """更新从指定日期到昨天的持仓历史、账户余额历史（不查询价格API）

        Args:
            start_date: 开始日期 "YYYY-MM-DD"
            ledger_id: 账本ID，None 表示所有账本
            account_id: 账户ID，None 表示所有账户
        """
        from datetime import datetime, timedelta

        try:
            yesterday = datetime.now() - timedelta(days=1)
            end_date = yesterday.strftime("%Y-%m-%d")

            if start_date > end_date:
                logging.info(f"开始日期 {start_date} 晚于昨天 {end_date}，无需更新历史")
                return

            self.generate_snapshots_only(start_date, end_date, ledger_id, account_id)
            self.generate_return_rate(
                ledger_id=ledger_id,
                full_refresh=True,
                write_to_db=True,
                incremental_from_date=start_date,
            )
            logging.info(
                f"已更新 {start_date} 到 {end_date} 的历史快照（账本: {ledger_id if ledger_id else '全部'}）"
            )
        except Exception as e:
            logging.error(f"更新历史快照失败: {e}")

    def add_transaction(self, transaction: Dict) -> bool:
        """添加交易记录（仅保存，不执行耗时计算）"""
        result = self.transaction_crud.add_transaction(transaction, self.analytics)
        if result:
            clear_related_cache(
                ledger_id=transaction.get("ledger_id"),
                account_id=transaction.get("account_id"),
            )
        return result

    def update_history_after_transaction(
        self, trans_date: str, ledger_id: Optional[int] = None
    ) -> None:
        """在添加交易后调用，更新历史数据（后台执行）"""
        self._update_history_for_date(trans_date, ledger_id=ledger_id)

    def get_transactions(
        self,
        ledger_id: Optional[int] = None,
        account_id: Optional[int] = None,
        trans_type: Optional[str] = None,
        category: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> pd.DataFrame:
        """获取交易记录"""
        return self.transaction_crud.get_transactions(
            ledger_id,
            account_id,
            trans_type,
            category,
            start_date,
            end_date,
            limit,
            offset,
        )

    def get_transactions_count(
        self,
        ledger_id: Optional[int] = None,
        account_id: Optional[int] = None,
        trans_type: Optional[str] = None,
        category: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> int:
        """获取交易记录总数（用于分页）"""
        return self.transaction_crud.get_transactions_count(
            ledger_id, account_id, trans_type, category, start_date, end_date
        )

    def get_transaction_by_id(self, transaction_id: int) -> Optional[Dict]:
        """根据ID获取单条交易记录"""
        return self.transaction_crud.get_transaction_by_id(transaction_id)

    def update_transaction(self, transaction_id: int, transaction: Dict) -> bool:
        """更新交易记录"""
        result = self.transaction_crud.update_transaction(
            transaction_id, transaction, self.analytics
        )
        if result:
            # 清除相关缓存
            clear_related_cache(
                ledger_id=transaction.get("ledger_id"),
                account_id=transaction.get("account_id"),
            )
            # 更新交易日期的历史数据
            trans_date = transaction.get("date")
            if trans_date:
                self._update_history_for_date(
                    trans_date, ledger_id=transaction.get("ledger_id")
                )
        return result

    def delete_transaction(
        self, transaction_id: int, rebuild_positions: bool = True
    ) -> bool:
        """删除交易记录并重新同步持仓"""
        transaction = self.get_transaction_by_id(transaction_id)
        trans_date = transaction.get("date") if transaction else None
        ledger_id = transaction.get("ledger_id") if transaction else None
        result = self.transaction_crud.delete_transaction(
            transaction_id, self.analytics, self, rebuild_positions
        )
        if result and transaction:
            clear_related_cache(
                ledger_id=ledger_id,
                account_id=transaction.get("account_id"),
            )
        return result

    def get_positions(
        self, ledger_id: Optional[int] = None, account_id: Optional[int] = None
    ) -> pd.DataFrame:
        """获取持仓信息"""
        return self.analytics.get_positions(ledger_id, account_id)

    def get_portfolio_stats(
        self, ledger_id: Optional[int] = None, account_id: Optional[int] = None
    ) -> Dict:
        """获取投资组合统计信息"""
        return self.analytics.get_portfolio_stats(ledger_id, account_id)

    def get_realized_pl(
        self, ledger_id: Optional[int] = None, account_id: Optional[int] = None
    ) -> Dict:
        """获取已实现损益汇总及明细"""
        return self.analytics.get_realized_pl(ledger_id, account_id)

    def update_position_price(self, position_id: int, new_price: float) -> bool:
        """更新持仓市价"""
        # 先获取持仓信息以便清除缓存
        positions = self.get_positions()
        position = (
            positions[positions["id"] == position_id] if not positions.empty else None
        )
        result = self.analytics.update_position_price(position_id, new_price)
        if result and position is not None and not position.empty:
            # 清除相关缓存
            clear_related_cache(
                ledger_id=position.iloc[0].get("ledger_id")
                if "ledger_id" in position.columns
                else None,
                account_id=position.iloc[0].get("account_id")
                if "account_id" in position.columns
                else None,
            )
        return result

    def _update_position(self, transaction: Dict):
        """使用 FIFO 或 WAC 框架更新持仓信息（根据账本设置）"""
        # 获取交易ID（需要从数据库查询最后插入的记录）
        cursor = self.conn.cursor()
        cursor.execute("SELECT MAX(id) FROM transactions")
        result = cursor.fetchone()
        transaction_id = result[0] if result and result[0] else 0
        self.analytics.update_position(transaction, transaction_id)

    def _rebuild_all_positions(self):
        """重建所有持仓（从库存管理器同步到数据库）"""
        self.analytics.rebuild_all_positions()

    def _rebuild_all_inventory(self):
        """从交易记录重建所有库存（FIFO 和 WAC）"""
        self.analytics._rebuild_all_inventory()

    def _get_inventory_manager(self, ledger_id: int):
        """根据账本的成本计算方法获取对应的库存管理器"""
        return self.analytics._get_inventory_manager(ledger_id)

    def fetch_market_price(self, code: str) -> Optional[float]:
        """
        从市场获取最新价格（昨日收盘价）

        Args:
            code: 股票代码，格式为 "市场.代码"，例如 "HK.00700", "SH.600519", "US.AAPL"

        Returns:
            最新收盘价，如果获取失败则返回 None
        """
        try:
            # 只获取昨日收盘价（今日未收盘）
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            start_date = end_date = yesterday

            # 解析股票代码
            separator = "."
            skip_separator = "-"

            # 检查是否包含跳过符号
            if skip_separator in code:
                logging.info(
                    f"⚠️ 代码包含跳过符号 '{skip_separator}'，跳过价格请求: {code}"
                )
                return None

            # 拆分市场类型和股票代码
            if separator in code:
                market, stock_code = code.split(separator, 1)
            else:
                # 如果没有市场前缀，默认为A股
                market = "A"
                stock_code = code

            # 获取价格数据
            result = get_stock_close_price(stock_code, start_date, end_date, market)

            if result is None or (isinstance(result, pd.DataFrame) and result.empty):
                logging.warning(f"⚠️ 无法获取 {code} 的价格数据")
                return None

            if isinstance(result, bool) and result is False:
                logging.error(f"❌ 获取 {code} 价格时发生错误")
                return None

            # 获取最新的价格（最后一行）
            if isinstance(result, pd.DataFrame) and not result.empty:
                latest_price = result.iloc[-1]["价格"]
                logging.info(f"✅ 成功获取 {code} 的最新价格: {latest_price}")
                return float(latest_price)

            return None

        except Exception as e:
            logging.error(f"❌ 获取市场价格时发生错误: {e}")
            return None

    def fetch_exchange_rate_from_market(self, currency: str) -> Optional[float]:
        """
        从市场获取最新汇率（昨日收盘价）

        Args:
            currency: 币种代码，例如 "USD", "HKD"

        Returns:
            最新汇率（相对于人民币），如果获取失败则返回 None
        """
        try:
            # 人民币不需要获取汇率
            if currency == "CNY":
                return 1.0

            # 只获取昨日汇率（今日未收盘）
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            start_date = end_date = yesterday

            # 获取汇率数据（使用中行汇买价）
            result = get_Settlement_exchange_rate(
                "中行汇买价", currency, start_date, end_date
            )

            if result is None or (isinstance(result, pd.DataFrame) and result.empty):
                logging.warning(f"⚠️ 无法获取 {currency} 的汇率数据")
                return None

            if isinstance(result, bool) and result is False:
                logging.error(f"❌ 获取 {currency} 汇率时发生错误")
                return None

            # 获取最新的汇率（最后一行）
            if isinstance(result, pd.DataFrame) and not result.empty:
                latest_rate = result.iloc[-1]["价格"]
                logging.info(f"✅ 成功获取 {currency} 的最新汇率: {latest_rate}")
                return float(latest_rate)

            return None

        except Exception as e:
            logging.error(f"❌ 获取汇率时发生错误: {e}")
            return None

    def update_all_positions_price(self) -> Dict[str, any]:
        """
        批量更新所有持仓的市场价格（使用昨日收盘价）

        Returns:
            更新结果统计
        """
        results = {
            "success_count": 0,
            "fail_count": 0,
            "success_list": [],
            "fail_list": [],
        }

        positions = self.get_positions()

        if positions.empty:
            logging.info("📭 没有持仓需要更新价格")
            return results

        for _, position in positions.iterrows():
            code = position["code"]
            position_id = position["id"]

            # 获取市场价格（昨日收盘价）
            new_price = self.fetch_market_price(code)

            if new_price is not None:
                # 更新价格
                if self.update_position_price(position_id, new_price):
                    results["success_count"] += 1
                    results["success_list"].append(
                        {"code": code, "name": position["name"], "new_price": new_price}
                    )
                else:
                    results["fail_count"] += 1
                    results["fail_list"].append(
                        {
                            "code": code,
                            "name": position["name"],
                            "reason": "数据库更新失败",
                        }
                    )
            else:
                results["fail_count"] += 1
                results["fail_list"].append(
                    {
                        "code": code,
                        "name": position["name"],
                        "reason": "无法获取市场价格",
                    }
                )

        logging.info(
            f"📊 价格更新完成: 成功 {results['success_count']} 个, 失败 {results['fail_count']} 个"
        )
        return results

    def update_all_exchange_rates(self) -> Dict[str, any]:
        """
        批量更新所有非CNY币种的汇率（使用昨日收盘价）。
        同时将获取到的汇率写入 exchange_rate_history，供交易记录使用历史汇率。

        Returns:
            更新结果统计
        """
        results = {
            "success_count": 0,
            "fail_count": 0,
            "success_list": [],
            "fail_list": [],
            "exchange_history_written": 0,
        }

        currencies = self.get_currencies()

        if currencies.empty:
            logging.info("📭 没有币种需要更新汇率")
            return results

        # 只获取昨日汇率（今日未收盘）
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        start_date = end_date = yesterday

        cursor = self.conn.cursor()
        for _, currency_row in currencies.iterrows():
            currency_code = currency_row["code"]

            # 跳过人民币
            if currency_code == "CNY":
                continue

            # 获取市场汇率（含历史日期范围，用于写入 exchange_rate_history）
            df = get_exchange_rate_range(currency_code, start_date, end_date)
            if df is None or df.empty:
                results["fail_count"] += 1
                results["fail_list"].append(
                    {
                        "code": currency_code,
                        "name": currency_row["name"],
                        "reason": "无法获取市场汇率",
                    }
                )
                continue

            new_rate = float(df.iloc[-1]["价格"])
            if self.update_exchange_rate(currency_code, new_rate):
                results["success_count"] += 1
                results["success_list"].append(
                    {
                        "code": currency_code,
                        "name": currency_row["name"],
                        "new_rate": new_rate,
                    }
                )
                # 写入 exchange_rate_history，供交易记录使用历史汇率
                for _, row in df.iterrows():
                    d, c, rate = str(row["日期"]), str(row["代码"]), float(row["价格"])
                    cursor.execute(
                        "INSERT OR REPLACE INTO exchange_rate_history (date, currency_code, rate) VALUES (?, ?, ?)",
                        (d, c, rate),
                    )
                results["exchange_history_written"] += len(df)
            else:
                results["fail_count"] += 1
                results["fail_list"].append(
                    {
                        "code": currency_code,
                        "name": currency_row["name"],
                        "reason": "数据库更新失败",
                    }
                )

        self.conn.commit()
        if results["exchange_history_written"] > 0:
            logging.info(
                f"💱 已写入 {results['exchange_history_written']} 条汇率历史到 exchange_rate_history"
            )
        logging.info(
            f"💱 汇率更新完成: 成功 {results['success_count']} 个, 失败 {results['fail_count']} 个"
        )
        return results

    # ============ 资金明细管理 ============

    def add_fund_transaction(self, fund_trans: Dict) -> bool:
        """添加资金明细记录（仅保存，不执行耗时计算）"""
        result = self.transaction_crud.add_fund_transaction(fund_trans, self.analytics)
        if result:
            clear_related_cache(
                ledger_id=fund_trans.get("ledger_id"),
                account_id=fund_trans.get("account_id"),
            )
        return result

    def update_fund_transaction(
        self, fund_trans_id: int, fund_trans: Dict
    ) -> bool:
        """更新资金明细（仅允许无关联交易的类型）。"""
        result = self.transaction_crud.update_fund_transaction(
            fund_trans_id, fund_trans, self.analytics
        )
        if result:
            clear_related_cache(
                ledger_id=fund_trans.get("ledger_id"),
            )
        return result

    def update_history_after_fund_transaction(
        self, fund_date: str, ledger_id: Optional[int] = None
    ) -> None:
        """在添加资金明细后调用，更新历史数据（后台执行）"""
        self._update_history_for_date(fund_date, ledger_id=ledger_id)

    def get_fund_transactions(
        self,
        ledger_id: Optional[int] = None,
        account_id: Optional[int] = None,
        trans_type: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> pd.DataFrame:
        """获取资金明细记录（支持多借多贷）"""
        return self.transaction_crud.get_fund_transactions(
            ledger_id, account_id, trans_type, start_date, end_date, limit, offset
        )

    def get_fund_transactions_count(
        self,
        ledger_id: Optional[int] = None,
        account_id: Optional[int] = None,
        trans_type: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> int:
        """获取资金明细记录总数（用于分页）"""
        return self.transaction_crud.get_fund_transactions_count(
            ledger_id, account_id, trans_type, start_date, end_date
        )

    def delete_fund_transaction(self, fund_trans_id: int) -> bool:
        """删除资金明细记录。若为开仓/平仓关联的资金明细，会同时删除对应交易记录并重建持仓。"""
        # 先获取资金明细信息以便清除缓存，并判断是否关联交易
        fund_trans = self.get_fund_transaction_by_id(fund_trans_id)
        fund_date = fund_trans.get("date") if fund_trans else None
        ledger_id = fund_trans.get("ledger_id") if fund_trans else None
        result = self.transaction_crud.delete_fund_transaction(fund_trans_id)
        if result and fund_trans:
            # 清除相关缓存
            clear_related_cache(
                ledger_id=ledger_id,
                account_id=fund_trans.get("account_id"),
            )
            # 若删除了关联的交易记录（开仓/平仓），需重建持仓
            if fund_trans.get("transaction_id"):
                self._rebuild_all_positions()
            # 更新资金明细日期的历史数据
            if fund_date:
                self._update_history_for_date(fund_date, ledger_id=ledger_id)
        return result

    def get_fund_transaction_by_id(self, fund_trans_id: int) -> Optional[Dict]:
        """根据ID获取单条资金明细记录（包含多借多贷明细）"""
        return self.transaction_crud.get_fund_transaction_by_id(fund_trans_id)

    def get_account_transaction_entries(
        self,
        account_id: int,
        trans_type: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> pd.DataFrame:
        """获取指定账户的资金变动明细"""
        return self.transaction_crud.get_account_transaction_entries(
            account_id, trans_type, start_date, end_date, limit, offset
        )

    def get_account_transaction_entries_count(
        self,
        account_id: int,
        trans_type: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> int:
        """获取账户变动明细总数"""
        return self.transaction_crud.get_account_transaction_entries_count(
            account_id, trans_type, start_date, end_date
        )

    def add_transaction_with_fund(self, transaction: Dict) -> bool:
        """添加交易记录并同时记录资金明细（仅保存，不执行耗时计算）"""
        result = self.transaction_crud.add_transaction_with_fund(
            transaction, self.analytics
        )
        if result:
            clear_related_cache(
                ledger_id=transaction.get("ledger_id"),
                account_id=transaction.get("account_id"),
            )
        return result

    def update_history_after_transaction_with_fund(
        self, trans_date: str, ledger_id: Optional[int] = None
    ) -> None:
        """在添加交易（带资金明细）后调用，更新历史数据（后台执行）"""
        self._update_history_for_date(trans_date, ledger_id=ledger_id)

    def get_account_balance(self, account_id: int) -> Dict:
        """获取账户资金余额统计（基于 fund_transaction_entries，现金与持仓在核心层区分）
        资金明细默认按现金核算：开仓/平仓只统计 subject_type='cash' 的分录。
        """
        cursor = self.conn.cursor()

        # 基于借贷分录表统计，开仓/平仓仅统计现金科目（subject_type='cash' 或 NULL 视为现金）
        cursor.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN ft.type = '本金投入' AND fte.side = 'debit' THEN fte.amount_cny ELSE 0 END), 0) as total_invest,
                COALESCE(SUM(CASE WHEN ft.type = '本金撤出' AND fte.side = 'credit' THEN fte.amount_cny ELSE 0 END), 0) as total_withdraw,
                COALESCE(SUM(CASE WHEN ft.type = '收入' AND fte.side = 'debit' THEN fte.amount_cny ELSE 0 END), 0) as total_income,
                COALESCE(SUM(CASE WHEN ft.type = '支出' AND fte.side = 'credit' THEN fte.amount_cny ELSE 0 END), 0) as total_expense,
                COALESCE(SUM(CASE WHEN ft.type = '内转' AND fte.side = 'credit' THEN fte.amount_cny ELSE 0 END), 0) as transfer_out,
                COALESCE(SUM(CASE WHEN ft.type = '内转' AND fte.side = 'debit' THEN fte.amount_cny ELSE 0 END), 0) as transfer_in,
                COALESCE(SUM(CASE WHEN ft.type = '开仓' AND fte.side = 'credit' AND COALESCE(fte.subject_type, 'cash') = 'cash' THEN fte.amount_cny ELSE 0 END), 0) as total_open,
                COALESCE(SUM(CASE WHEN ft.type = '平仓' AND fte.side = 'debit' AND COALESCE(fte.subject_type, 'cash') = 'cash' THEN fte.amount_cny ELSE 0 END), 0) as total_close
            FROM fund_transactions ft
            JOIN fund_transaction_entries fte ON ft.id = fte.fund_transaction_id
            WHERE fte.account_id = ?
        """,
            (account_id,),
        )

        row = cursor.fetchone()
        if row:
            total_invest, total_withdraw, total_income, total_expense = (
                row[0],
                row[1],
                row[2],
                row[3],
            )
            transfer_out, transfer_in, total_open, total_close = (
                row[4],
                row[5],
                row[6],
                row[7],
            )
            balance = (
                total_invest
                - total_withdraw
                + total_income
                - total_expense
                - transfer_out
                + transfer_in
                - total_open
                + total_close
            )
            return {
                "total_invest": total_invest,
                "total_withdraw": total_withdraw,
                "total_income": total_income,
                "total_expense": total_expense,
                "transfer_out": transfer_out,
                "transfer_in": transfer_in,
                "total_open": total_open,
                "total_close": total_close,
                "balance": balance,
            }
        return {
            "total_invest": 0,
            "total_withdraw": 0,
            "total_income": 0,
            "total_expense": 0,
            "transfer_out": 0,
            "transfer_in": 0,
            "total_open": 0,
            "total_close": 0,
            "balance": 0,
        }

    # ============ 历史价格与历史快照 ============

    def _get_missing_price_date_range(
        self,
        start_date: str,
        end_date: str,
        codes: List[str],
        currencies: List[str],
    ) -> tuple:
        """
        获取价格缺失的最小日期和最大日期范围。
        只有当某日所有证券代码都有价格且所有币种都有汇率时，该日才视为完整；否则视为缺失。

        Args:
            start_date: 开始日期 "YYYY-MM-DD"
            end_date: 结束日期 "YYYY-MM-DD"
            codes: 证券代码列表
            currencies: 币种代码列表

        Returns:
            (missing_start, missing_end): 缺失的最小日期和最大日期，如果没有缺失则返回 (None, None)
        """
        cursor = self.conn.cursor()

        # 生成日期范围内的所有日期
        all_dates = set()
        for d in pd.date_range(start=start_date, end=end_date):
            all_dates.add(d.strftime("%Y-%m-%d"))

        if not all_dates:
            return None, None

        all_currencies = currencies + ["CNY"] if "CNY" not in currencies else currencies

        # 证券价格：某日完整 = 该日所有 codes 都有价格
        security_complete_dates = set()
        if codes:
            placeholders = ",".join("?" * len(codes))
            cursor.execute(
                f"""
                SELECT date FROM security_price_history
                WHERE date >= ? AND date <= ? AND code IN ({placeholders})
                GROUP BY date
                HAVING COUNT(DISTINCT code) = ?
            """,
                [start_date, end_date] + codes + [len(codes)],
            )
            security_complete_dates = {row[0] for row in cursor.fetchall()}
        else:
            security_complete_dates = all_dates

        # 汇率：某日完整 = 该日所有 currencies 都有汇率
        exchange_complete_dates = set()
        if all_currencies:
            placeholders = ",".join("?" * len(all_currencies))
            cursor.execute(
                f"""
                SELECT date FROM exchange_rate_history
                WHERE date >= ? AND date <= ? AND currency_code IN ({placeholders})
                GROUP BY date
                HAVING COUNT(DISTINCT currency_code) = ?
            """,
                [start_date, end_date] + all_currencies + [len(all_currencies)],
            )
            exchange_complete_dates = {row[0] for row in cursor.fetchall()}
        else:
            exchange_complete_dates = all_dates

        # 某日完整 = 证券和汇率都完整
        complete_dates = security_complete_dates & exchange_complete_dates
        missing_dates = all_dates - complete_dates

        if not missing_dates:
            return None, None

        return min(missing_dates), max(missing_dates)

    def backfill_prices_for_dates(
        self,
        start_date: str,
        end_date: str,
        ledger_id: Optional[int] = None,
        account_id: Optional[int] = None,
    ) -> Dict[str, int]:
        """
        补全日期范围内缺失的证券价格和外汇汇率，写入 security_price_history / exchange_rate_history。
        只获取缺失的最小日期和最大日期范围内的价格，避免重复获取已有价格。
        使用 utils.get_market_price 中的 get_stock_close_price_range、get_exchange_rate_range 获取数据。

        Args:
            start_date: 开始日期 "YYYY-MM-DD"
            end_date: 结束日期 "YYYY-MM-DD"
            ledger_id: 可选，仅补全该账本持仓涉及的代码
            account_id: 可选，仅补全该账户持仓涉及的代码

        Returns:
            {"security_inserted": N, "exchange_inserted": M}
        """
        cursor = self.conn.cursor()
        security_inserted = 0
        exchange_inserted = 0

        # 需要补全的证券代码：从持仓或历史持仓中取
        if ledger_id is not None or account_id is not None:
            q = """
                SELECT DISTINCT p.code FROM positions p
                WHERE p.quantity != 0
            """
            params = []
            if ledger_id is not None:
                q += " AND p.ledger_id = ?"
                params.append(ledger_id)
            if account_id is not None:
                q += " AND p.account_id = ?"
                params.append(account_id)
            codes_df = pd.read_sql_query(q, self.conn, params=params)
        else:
            codes_df = pd.read_sql_query(
                "SELECT DISTINCT code FROM positions WHERE quantity != 0", self.conn
            )
        codes = codes_df["code"].tolist() if not codes_df.empty else []

        # 需要补全的币种：从 currencies 取非 CNY
        currencies_df = pd.read_sql_query(
            "SELECT code FROM currencies WHERE code != 'CNY'", self.conn
        )
        currencies = currencies_df["code"].tolist() if not currencies_df.empty else []

        # 确定实际需要获取价格的日期范围（只获取缺失的部分）
        missing_start, missing_end = self._get_missing_price_date_range(
            start_date, end_date, codes, currencies
        )

        if missing_start is None:
            logging.info(f"价格数据已完整覆盖 {start_date} 到 {end_date}，无需补全")
            return {"security_inserted": 0, "exchange_inserted": 0}

        logging.info(f"价格缺失范围: {missing_start} 到 {missing_end}，开始补全...")

        skip_separator = "-"
        for code in codes:
            if skip_separator in code:
                continue
            df = get_stock_close_price_range(code, missing_start, missing_end)
            if df is None or df.empty:
                continue
            for _, row in df.iterrows():
                d, c, price = str(row["日期"]), str(row["代码"]), float(row["价格"])
                cursor.execute(
                    "INSERT OR IGNORE INTO security_price_history (date, code, price) VALUES (?, ?, ?)",
                    (d, c, price),
                )
                if cursor.rowcount:
                    security_inserted += 1

        for currency_code in currencies:
            df = get_exchange_rate_range(currency_code, missing_start, missing_end)
            if df is None or df.empty:
                continue
            for _, row in df.iterrows():
                d, c, rate = str(row["日期"]), str(row["代码"]), float(row["价格"])
                cursor.execute(
                    "INSERT OR IGNORE INTO exchange_rate_history (date, currency_code, rate) VALUES (?, ?, ?)",
                    (d, c, rate),
                )
                if cursor.rowcount:
                    exchange_inserted += 1

        # CNY 固定为 1.0，补全日期范围内缺失的
        for d in pd.date_range(start=missing_start, end=missing_end):
            ds = d.strftime("%Y-%m-%d")
            cursor.execute(
                "INSERT OR IGNORE INTO exchange_rate_history (date, currency_code, rate) VALUES (?, ?, ?)",
                (ds, "CNY", 1.0),
            )
            if cursor.rowcount:
                exchange_inserted += 1

        self.conn.commit()
        logging.info(
            f"历史价格补全: 证券 {security_inserted} 条, 汇率 {exchange_inserted} 条"
        )
        return {
            "security_inserted": security_inserted,
            "exchange_inserted": exchange_inserted,
        }

    def _get_price_at_date(self, code: str, date: str) -> Optional[float]:
        """从 security_price_history 取某日证券价格，无则尝试从交易记录获取"""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT price FROM security_price_history WHERE date = ? AND code = ?",
            (date, code),
        )
        row = cursor.fetchone()
        if row:
            return float(row[0])
        cursor.execute(
            """
            SELECT price FROM security_price_history
            WHERE code = ? AND date <= ?
            ORDER BY date DESC LIMIT 1
        """,
            (code, date),
        )
        row = cursor.fetchone()
        if row:
            return float(row[0])
        cursor.execute(
            """
            SELECT price FROM transactions
            WHERE code = ? AND date <= ?
            ORDER BY date DESC LIMIT 1
        """,
            (code, date),
        )
        row = cursor.fetchone()
        return float(row[0]) if row else None

    def _get_rate_at_date(self, currency_code: str, date: str) -> float:
        """从 exchange_rate_history 取某日汇率，无则使用默认汇率"""
        if currency_code == "CNY":
            return 1.0
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT rate FROM exchange_rate_history WHERE date = ? AND currency_code = ?",
            (date, currency_code),
        )
        row = cursor.fetchone()
        if row:
            return float(row[0])
        cursor.execute(
            """
            SELECT rate FROM exchange_rate_history
            WHERE currency_code = ? AND date <= ?
            ORDER BY date DESC LIMIT 1
        """,
            (currency_code, date),
        )
        row = cursor.fetchone()
        if row:
            return float(row[0])
        return DEFAULT_EXCHANGE_RATES.get(currency_code, 1.0)

    def get_latest_rate_before_date(
        self, currency_code: str, target_date: str
    ) -> Optional[float]:
        """
        获取指定日期之前（含）最新的汇率
        用于交易记录使用历史汇率
        """
        if currency_code == "CNY":
            return 1.0
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT rate FROM exchange_rate_history
            WHERE currency_code = ? AND date <= ?
            ORDER BY date DESC LIMIT 1
        """,
            (currency_code, target_date),
        )
        row = cursor.fetchone()
        return float(row[0]) if row else None

    def recalculate_transaction_rates(self, start_date: str, end_date: str) -> int:
        """
        重新计算指定日期范围内所有外币交易的汇率。
        当补全历史汇率数据后，可调用此方法将 transactions 和 fund_transaction_entries 中的 amount_cny 同步更新。
        """
        cursor = self.conn.cursor()
        updated = 0

        # 1. 更新 transactions 表（开仓/平仓等证券交易）
        cursor.execute(
            """
            SELECT t.id, c.code, t.date, t.amount, t.amount_cny
            FROM transactions t
            JOIN currencies c ON t.currency_id = c.id
            WHERE c.code != 'CNY'
              AND t.date BETWEEN ? AND ?
        """,
            (start_date, end_date),
        )

        for trans_id, currency_code, date, amount, old_amount_cny in cursor.fetchall():
            new_rate = self.get_latest_rate_before_date(currency_code, date)
            if new_rate is not None:
                new_amount_cny = amount * new_rate
                if abs(new_amount_cny - old_amount_cny) > 0.01:
                    cursor.execute(
                        """
                        UPDATE transactions SET amount_cny = ?
                        WHERE id = ?
                    """,
                        (new_amount_cny, trans_id),
                    )
                    updated += 1

        # 2. 更新 fund_transaction_entries 表（收入/支出/内转/开仓/平仓的资金明细）
        cursor.execute(
            """
            SELECT ft.id, c.code, ft.date
            FROM fund_transactions ft
            JOIN currencies c ON ft.currency_id = c.id
            WHERE c.code != 'CNY'
              AND ft.date BETWEEN ? AND ?
        """,
            (start_date, end_date),
        )

        for ft_id, currency_code, date in cursor.fetchall():
            new_rate = self.get_latest_rate_before_date(currency_code, date)
            if new_rate is not None:
                cursor.execute(
                    """
                    SELECT id, amount, amount_cny FROM fund_transaction_entries
                    WHERE fund_transaction_id = ?
                """,
                    (ft_id,),
                )
                for entry_id, amount, old_amount_cny in cursor.fetchall():
                    new_amount_cny = amount * new_rate
                    if abs(new_amount_cny - old_amount_cny) > 0.01:
                        cursor.execute(
                            """
                            UPDATE fund_transaction_entries SET amount_cny = ?
                            WHERE id = ?
                        """,
                            (new_amount_cny, entry_id),
                        )
                        updated += 1

        self.conn.commit()
        logging.info(f"已更新 {updated} 条交易/资金记录的汇率")
        if updated > 0:
            # 重建库存和持仓，使成本计算使用更正后的历史汇率
            self._rebuild_all_positions()
        return updated

    def save_position_history_snapshot(
        self,
        as_of_date: str,
        ledger_id: Optional[int] = None,
        account_id: Optional[int] = None,
        backfill_if_missing: bool = True,
    ) -> int:
        """
        保存某日持仓历史快照到 position_history。
        会按账本计算截至 as_of_date 的持仓，并补全缺失的证券价格与汇率（若 backfill_if_missing 为 True）。

        Args:
            as_of_date: 快照日期 "YYYY-MM-DD"
            ledger_id: 可选，不传则对所有账本分别快照
            account_id: 可选
            backfill_if_missing: 是否在缺失时调用市场接口补全价格/汇率

        Returns:
            写入的 position_history 行数
        """
        ledgers_df = self.get_ledgers()
        if ledgers_df.empty:
            return 0
        if ledger_id is not None:
            ledgers_df = ledgers_df[ledgers_df["id"] == ledger_id]
        if ledgers_df.empty:
            return 0

        if backfill_if_missing:
            self.backfill_prices_for_dates(
                as_of_date, as_of_date, ledger_id, account_id
            )

        cursor = self.conn.cursor()
        inserted = 0
        currencies_df = pd.read_sql_query("SELECT id, code FROM currencies", self.conn)
        currency_id_to_code = dict(zip(currencies_df["id"], currencies_df["code"]))

        for _, ledger_row in ledgers_df.iterrows():
            lid = ledger_row["id"]
            positions = self.analytics.get_positions_as_of_date(
                as_of_date, ledger_id=lid, account_id=account_id
            )
            for pos in positions:
                code = pos["code"]
                currency_id = pos["currency_id"]
                currency_code = currency_id_to_code.get(currency_id, "CNY")
                price_at = self._get_price_at_date(code, as_of_date)
                rate_at = self._get_rate_at_date(currency_code, as_of_date)
                if price_at is None or rate_at is None:
                    continue
                qty = pos["quantity"]
                market_value_local = qty * price_at
                market_value_cny = market_value_local * rate_at
                cursor.execute(
                    """
                    INSERT INTO position_history
                    (date, ledger_id, account_id, code, name, category_id, currency_id,
                     quantity, avg_cost, price_at_date, market_value_local, rate_at_date, market_value_cny)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        as_of_date,
                        pos["ledger_id"],
                        pos["account_id"],
                        pos["code"],
                        pos["name"],
                        pos["category_id"],
                        pos["currency_id"],
                        qty,
                        pos["avg_cost"],
                        price_at,
                        market_value_local,
                        rate_at,
                        market_value_cny,
                    ),
                )
                inserted += 1

        self.conn.commit()
        logging.info(f"持仓历史快照: {as_of_date} 写入 {inserted} 条")
        return inserted

    def get_account_balance_as_of_date(
        self,
        account_id: int,
        as_of_date: str,
        exclude_ft_types: Optional[tuple] = None,
    ) -> float:
        """获取某日账户现金余额（人民币），基于 fund_transaction_entries。

        计算逻辑：先按币种汇总外币金额，再用当日汇率转换为人民币。
        这样每天的余额会随汇率波动而变化。

        Args:
            account_id: 账户ID
            as_of_date: 截止日期
            exclude_ft_types: 排除的 fund_transactions 类型，如 ('本金投入','本金撤出')，
                用于权益类账户时仅汇总开仓/平仓等证券相关现金，不汇总本金投入/撤出。
        """
        cursor = self.conn.cursor()
        excl_sql = ""
        params: list = [account_id, as_of_date]
        if exclude_ft_types:
            placeholders = ",".join("?" * len(exclude_ft_types))
            excl_sql = f" AND ft.type NOT IN ({placeholders})"
            params.extend(exclude_ft_types)

        cursor.execute(
            f"""
            SELECT
                fte.currency_code,
                COALESCE(SUM(CASE WHEN fte.side = 'debit' THEN fte.amount ELSE -fte.amount END), 0) as amount
            FROM (
                SELECT 
                    fte.side,
                    fte.amount,
                    c.code as currency_code
                FROM fund_transaction_entries fte
                JOIN fund_transactions ft ON fte.fund_transaction_id = ft.id
                JOIN currencies c ON ft.currency_id = c.id
                WHERE fte.account_id = ? AND ft.date <= ?
                  AND COALESCE(fte.subject_type, 'cash') = 'cash'
                  {excl_sql}
            ) fte
            GROUP BY fte.currency_code
            """,
            params,
        )

        total_cny = 0.0
        for currency_code, amount in cursor.fetchall():
            amount_val = float(amount)
            if currency_code == "CNY":
                total_cny += amount_val
            else:
                # 外币（含负现金余额）必须计入当日净资产，否则会高估
                # 如：港币-500买腾讯时，-500 HKD 必须按汇率折算，否则净值为 0.92*500+1000 而非正确的 1000
                rate = self._get_rate_at_date(currency_code or "CNY", as_of_date)
                total_cny += amount_val * (rate if rate is not None else DEFAULT_EXCHANGE_RATES.get(currency_code or "CNY", 1.0))

        return total_cny

    def get_first_balance_date(self) -> Optional[str]:
        """获取第一条有余额的日期（从 fund_transaction_entries 中查找）。"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT MIN(ft.date) 
            FROM fund_transactions ft
            JOIN fund_transaction_entries fte ON ft.id = fte.fund_transaction_id
            WHERE fte.amount != 0
        """)
        row = cursor.fetchone()
        return row[0] if row and row[0] else None

    def get_first_transaction_date(self) -> Optional[str]:
        """获取第一条证券交易日期（从 transactions 中查找，用于确定持仓价格补全的起始范围）。"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT MIN(date) FROM transactions")
        row = cursor.fetchone()
        return row[0] if row and row[0] else None

    def get_earliest_date_for_backfill(self) -> Optional[str]:
        """获取历史数据补全的起始日期：余额和交易两者中最早的那天。"""
        balance_date = self.get_first_balance_date()
        trans_date = self.get_first_transaction_date()
        dates = [d for d in (balance_date, trans_date) if d]
        return min(dates) if dates else None

    def save_account_balance_history(self, as_of_date: str) -> int:
        """保存某日所有账户余额到 account_balance_history。
        权益类账户仅保存开仓/平仓相关现金（排除本金投入/撤出），与 get_daily_assets 一致。
        """
        from utils.equity_blacklist import is_equity_account

        accounts_df = pd.read_sql_query("SELECT id, name FROM accounts", self.conn)
        if accounts_df.empty:
            return 0
        cursor = self.conn.cursor()
        inserted = 0
        for _, row in accounts_df.iterrows():
            aid, name = row["id"], row["name"]
            if is_equity_account(name or ""):
                balance = self.get_account_balance_as_of_date(
                    aid, as_of_date, exclude_ft_types=("本金投入", "本金撤出")
                )
            else:
                balance = self.get_account_balance_as_of_date(aid, as_of_date)
            cursor.execute(
                "INSERT OR REPLACE INTO account_balance_history (date, account_id, balance_cny) VALUES (?, ?, ?)",
                (as_of_date, aid, balance),
            )
            inserted += 1
        self.conn.commit()
        logging.info(f"账户余额历史快照: {as_of_date} 写入 {inserted} 条")
        return inserted

    def save_position_and_balance_history_range(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        ledger_id: Optional[int] = None,
        account_id: Optional[int] = None,
    ) -> Dict[str, int]:
        """
        保存日期范围内的历史持仓快照和账户余额到数据库。
        如果未指定日期范围，默认从第一条有余额的日期到昨天。

        Args:
            start_date: 开始日期 "YYYY-MM-DD"，为 None 则自动获取第一条有余额的日期
            end_date: 结束日期 "YYYY-MM-DD"，为 None 则使用昨天
            ledger_id: 可选，仅保存该账本的数据
            account_id: 可选，仅保存该账户的数据

        Returns:
            {"position_count": N, "balance_count": M, "start_date": start_date, "end_date": end_date}
        """
        from datetime import datetime, timedelta

        # 确定日期范围
        if start_date is None:
            first_date = self.get_first_balance_date()
            if first_date is None:
                logging.warning("没有找到第一条有余额的日期")
                return {
                    "position_count": 0,
                    "balance_count": 0,
                    "start_date": None,
                    "end_date": None,
                }
            start_date = first_date

        if end_date is None:
            yesterday = datetime.now() - timedelta(days=1)
            end_date = yesterday.strftime("%Y-%m-%d")
        else:
            # 结束日期不得超过昨天（今日价格未收盘，无法生成有效快照）
            yesterday = datetime.now() - timedelta(days=1)
            yesterday_str = yesterday.strftime("%Y-%m-%d")
            if end_date > yesterday_str:
                logging.warning(
                    f"结束日期 {end_date} 超过昨天 {yesterday_str}，已自动截断为昨天"
                )
                end_date = yesterday_str

        logging.info(f"开始保存历史持仓和账户余额: {start_date} 到 {end_date}")

        # 首先补全日期范围内缺失的价格
        self.backfill_prices_for_dates(start_date, end_date, ledger_id, account_id)
        # 同步更正交易记录的 amount_cny，并重建库存（使成本计算使用最新历史汇率）
        self.recalculate_transaction_rates(start_date, end_date)

        position_count = 0
        balance_count = 0

        # 遍历日期范围内的每一天
        for single_date in pd.date_range(start=start_date, end=end_date):
            date_str = single_date.strftime("%Y-%m-%d")

            # 保存持仓快照
            pos_n = self.save_position_history_snapshot(
                date_str, ledger_id, account_id, backfill_if_missing=False
            )
            position_count += pos_n

            # 保存账户余额
            bal_n = self.save_account_balance_history(date_str)
            balance_count += bal_n

        logging.info(
            f"历史数据保存完成: 持仓 {position_count} 条, 账户余额 {balance_count} 条"
        )
        return {
            "position_count": position_count,
            "balance_count": balance_count,
            "start_date": start_date,
            "end_date": end_date,
        }

    def generate_snapshots_only(
        self,
        start_date: str,
        end_date: Optional[str] = None,
        ledger_id: Optional[int] = None,
        account_id: Optional[int] = None,
    ) -> Dict[str, int]:
        """
        仅生成历史持仓和账户余额快照（不查询价格API）。
        用于交易增删改后快速更新历史快照。

        Args:
            start_date: 开始日期 "YYYY-MM-DD"
            end_date: 结束日期 "YYYY-MM-DD"，为 None 则使用昨天
            ledger_id: 可选，仅保存该账本的数据
            account_id: 可选，仅保存该账户的数据

        Returns:
            {"position_count": N, "balance_count": M, "start_date": start_date, "end_date": end_date}
        """
        from datetime import datetime, timedelta

        if end_date is None:
            yesterday = datetime.now() - timedelta(days=1)
            end_date = yesterday.strftime("%Y-%m-%d")
        else:
            yesterday = datetime.now() - timedelta(days=1)
            yesterday_str = yesterday.strftime("%Y-%m-%d")
            if end_date > yesterday_str:
                end_date = yesterday_str

        logging.info(f"开始生成历史快照: {start_date} 到 {end_date}")

        position_count = 0
        balance_count = 0

        for single_date in pd.date_range(start=start_date, end=end_date):
            date_str = single_date.strftime("%Y-%m-%d")

            pos_n = self.save_position_history_snapshot(
                date_str, ledger_id, account_id, backfill_if_missing=False
            )
            position_count += pos_n

            bal_n = self.save_account_balance_history(date_str)
            balance_count += bal_n

        logging.info(
            f"历史快照生成完成: 持仓 {position_count} 条, 账户余额 {balance_count} 条"
        )
        return {
            "position_count": position_count,
            "balance_count": balance_count,
            "start_date": start_date,
            "end_date": end_date,
        }

    def auto_backfill_history_and_snapshots(self) -> Dict[str, any]:
        """
        自动补全历史价格和快照（不含今日）。
        从缺失价格的最早日期到昨天，自动补全缺失的历史价格并保存持仓/余额快照。
        搜索起点为余额和交易两者中最早的那天。
        通常在更新价格后自动调用。

        Returns:
            {
                "price_result": {"security_inserted": N, "exchange_inserted": M},
                "snapshot_result": {"position_count": P, "balance_count": B, "start_date": "...", "end_date": "..."}
            }
        """
        from datetime import datetime, timedelta

        logging.info("开始自动补全历史价格和快照...")

        # 获取日期范围：从缺失价格的最早日期到昨天（使用余额和交易两者中最早的那天作为搜索起点）
        start_date = self.get_earliest_date_for_backfill()
        if start_date is None:
            logging.warning("自动补全：没有找到第一条有余额的日期，跳过")
            return {
                "price_result": {"security_inserted": 0, "exchange_inserted": 0},
                "snapshot_result": {
                    "position_count": 0,
                    "balance_count": 0,
                    "start_date": None,
                    "end_date": None,
                },
            }

        yesterday = datetime.now() - timedelta(days=1)
        end_date = yesterday.strftime("%Y-%m-%d")

        # 如果开始日期晚于昨天（没有历史数据需要补全），直接返回
        if start_date > end_date:
            logging.info("自动补全：开始日期晚于昨天，无需补全")
            return {
                "price_result": {"security_inserted": 0, "exchange_inserted": 0},
                "snapshot_result": {
                    "position_count": 0,
                    "balance_count": 0,
                    "start_date": start_date,
                    "end_date": end_date,
                },
            }

        # 1. 补全历史价格（只补全缺失的部分）
        price_result = self.backfill_prices_for_dates(start_date, end_date)

        # 1.5 同步更正交易记录的 amount_cny（一键更新汇率后或补全汇率后，交易记录需使用最新历史汇率）
        recalc_count = self.recalculate_transaction_rates(start_date, end_date)
        if recalc_count > 0:
            logging.info(f"已更正 {recalc_count} 条交易/资金记录的汇率")

        # 2. 保存历史持仓和余额快照
        snapshot_result = self.save_position_and_balance_history_range(
            start_date, end_date
        )

        logging.info(
            f"自动补全完成: 证券价格 {price_result['security_inserted']} 条, "
            f"汇率 {price_result['exchange_inserted']} 条, "
            f"交易汇率更正 {recalc_count} 条, "
            f"持仓快照 {snapshot_result['position_count']} 条, "
            f"余额快照 {snapshot_result['balance_count']} 条"
        )

        return {
            "price_result": price_result,
            "snapshot_result": snapshot_result,
            "recalc_count": recalc_count,
        }

    def get_position_history(
        self,
        ledger_id: Optional[int] = None,
        account_id: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """查询历史持仓快照。"""
        q = "SELECT * FROM position_history WHERE 1=1"
        params = []
        if ledger_id is not None:
            q += " AND ledger_id = ?"
            params.append(ledger_id)
        if account_id is not None:
            q += " AND account_id = ?"
            params.append(account_id)
        if start_date:
            q += " AND date >= ?"
            params.append(start_date)
        if end_date:
            q += " AND date <= ?"
            params.append(end_date)
        q += " ORDER BY date, ledger_id, account_id, code"
        return pd.read_sql_query(q, self.conn, params=params)

    def get_account_balance_history(
        self,
        account_id: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """查询历史账户余额。"""
        q = "SELECT * FROM account_balance_history WHERE 1=1"
        params = []
        if account_id is not None:
            q += " AND account_id = ?"
            params.append(account_id)
        if start_date:
            q += " AND date >= ?"
            params.append(start_date)
        if end_date:
            q += " AND date <= ?"
            params.append(end_date)
        q += " ORDER BY date, account_id"
        return pd.read_sql_query(q, self.conn, params=params)

    # ============ 收益率统计（净值法） ============

    def get_daily_assets(self, ledger_id: int, as_of_date: str) -> tuple:
        """
        计算某日某账本的当日净资产 = 资产类 - 负债类。
        资产类 = 资产类账户现金余额 + 持仓市值（每日持仓 × 当日价格）；负债类 = 负债类账户余额。
        不依赖预存的快照表，当 account_balance_history / position_history 无数据时用此方法实时计算。

        Args:
            ledger_id: 账本ID
            as_of_date: 日期 "YYYY-MM-DD"

        Returns:
            tuple: (balance_cny, position_value_cny)，其中 balance_cny 为资产类现金-负债类现金，
                   position_value_cny 为当日持仓按当日价格折算的市值；当日净资产 = balance_cny + position_value_cny。
        """
        cursor = self.conn.cursor()
        from utils.equity_blacklist import is_equity_account

        # 1. 账户余额：按类型区分。资产类、负债类、权益类均加余额（余额=借方-贷方，负债为贷方余额故为负，加即等价于减负债）；收入/支出不参与净资产。
        cursor.execute(
            "SELECT id, name, type FROM accounts WHERE ledger_id = ?", (ledger_id,)
        )
        account_rows = cursor.fetchall()
        balance_cny = 0.0
        for aid, name, acc_type in account_rows:
            acc_type = (acc_type or "").strip()
            name = name or ""
            if acc_type in ("收入", "支出"):
                continue
            if is_equity_account(name):
                balance_cny += self.get_account_balance_as_of_date(
                    aid, as_of_date, exclude_ft_types=("本金投入", "本金撤出")
                )
            else:
                # 资产、负债及其他：余额=借方-贷方，负债账户为负，加总即得 资产-负债
                balance_cny += self.get_account_balance_as_of_date(aid, as_of_date)

        # 2. 持仓市值：按当日持仓 × 当日价格计算（资产类根据每日持仓和价格）
        positions = self.analytics.get_positions_as_of_date(
            as_of_date, ledger_id=ledger_id
        )
        currencies_df = pd.read_sql_query("SELECT id, code FROM currencies", self.conn)
        currency_id_to_code = dict(zip(currencies_df["id"], currencies_df["code"]))

        position_value_cny = 0.0
        for pos in positions:
            code = pos["code"]
            currency_id = pos["currency_id"]
            currency_code = currency_id_to_code.get(currency_id, "CNY")
            price_at = self._get_price_at_date(code, as_of_date)
            rate_at = self._get_rate_at_date(currency_code, as_of_date)
            if price_at is None or rate_at is None:
                continue
            qty = pos["quantity"]
            market_value_cny = qty * price_at * rate_at
            position_value_cny += market_value_cny

        return (balance_cny, position_value_cny)

    def generate_return_rate(
        self,
        ledger_id: Optional[int] = None,
        full_refresh: bool = True,
        write_to_db: bool = True,
        incremental_from_date: Optional[str] = None,
    ):
        """
        按 process_return_rate.py 的净值法计算收益率，写入 return_rate 表。
        支持增量：指定 incremental_from_date 且指定 ledger_id 时，仅重算该日至今。

        前置条件：需先运行 auto_backfill_history_and_snapshots() 生成
        position_history 和 account_balance_history；且需有本金投入/撤出记录（资金明细）。

        Args:
            ledger_id: 账本ID，None 表示处理所有账本
            full_refresh: 是否全量刷新（增量时仅删除指定日及之后）
            write_to_db: 是否写入数据库
            incremental_from_date: 增量起始日期 "YYYY-MM-DD"，与 ledger_id 同时指定时仅重算该日至今
        """
        from return_rate_sqlite import generate_return_rate as _generate

        return _generate(
            self.conn,
            ledger_id=ledger_id,
            full_refresh=full_refresh,
            write_to_db=write_to_db,
            db=self,
            incremental_from_date=incremental_from_date,
        )

    def get_return_rate(
        self,
        ledger_id: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        获取收益率数据（来自 return_rate 表，需先调用 generate_return_rate）。

        Args:
            ledger_id: 账本ID，None 表示全部
            start_date: 开始日期 YYYY-MM-DD
            end_date: 结束日期 YYYY-MM-DD

        Returns:
            pd.DataFrame: 收益率数据
        """
        from return_rate_sqlite import get_return_rate_df

        df = get_return_rate_df(self.conn, ledger_id)
        if df.empty:
            return df
        if start_date:
            df = df[df["date"] >= start_date]
        if end_date:
            df = df[df["date"] <= end_date]
        return df.reset_index(drop=True)

    def get_latest_cumulative_return(
        self, ledger_id: Optional[int] = None
    ) -> Optional[float]:
        """
        获取最新日期的累计收益率（净值法），若未计算过则返回 None。
        """
        df = self.get_return_rate(ledger_id=ledger_id)
        if df.empty:
            return None
        last = df.iloc[-1]
        return (
            float(last.get("累计收益率", 0))
            if pd.notna(last.get("累计收益率"))
            else None
        )

    def clear_all_data(self) -> bool:
        """
        清空数据库中所有业务数据，保留表结构并重新初始化默认币种和投资类别。
        此操作不可恢复，请谨慎使用。

        Returns:
            bool: 是否成功
        """
        try:
            cursor = self.conn.cursor()

            # 按外键依赖顺序删除（子表先删）
            tables_to_clear = [
                "fund_transaction_entries",
                "fund_transactions",
                "transactions",
                "positions",
                "position_history",
                "account_balance_history",
                "return_rate",
                "rounding_diff",
                "accounts",
                "ledgers",
                "security_price_history",
                "exchange_rate_history",
                "categories",
                "currencies",
            ]

            # SQLite 需要临时关闭外键检查
            if self.db_type == "sqlite":
                cursor.execute("PRAGMA foreign_keys = OFF")

            for table in tables_to_clear:
                try:
                    if self.db_type == "postgresql":
                        cursor.execute(f'TRUNCATE TABLE "{table}" CASCADE')
                    else:
                        cursor.execute(f"DELETE FROM {table}")
                except Exception as e:
                    # 表可能不存在（如旧版本迁移未完成），跳过
                    logging.warning(f"清空表 {table} 时跳过: {e}")

            if self.db_type == "sqlite":
                cursor.execute("PRAGMA foreign_keys = ON")

            # 重新初始化默认币种
            currency_info = {
                "CNY": ("人民币", "¥"),
                "HKD": ("港币", "HK$"),
                "USD": ("美元", "$"),
                "EUR": ("欧元", "€"),
                "GBP": ("英镑", "£"),
                "JPY": ("日元", "¥"),
            }
            for code, rate in DEFAULT_EXCHANGE_RATES.items():
                name, symbol = currency_info.get(code, (code, code))
                if self.db_type == "postgresql":
                    cursor.execute(
                        """
                        INSERT INTO currencies (code, name, symbol, exchange_rate)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (code) DO NOTHING
                        """,
                        (code, name, symbol, rate),
                    )
                else:
                    cursor.execute(
                        """
                        INSERT OR IGNORE INTO currencies (code, name, symbol, exchange_rate)
                        VALUES (?, ?, ?, ?)
                        """,
                        (code, name, symbol, rate),
                    )

            # 重新初始化默认投资类别
            default_categories = [
                ("股票", "股票投资"),
                ("基金", "基金投资"),
                ("债券", "债券投资"),
                ("加密货币", "加密货币投资"),
                ("银行理财", "银行理财产品"),
                ("其他", "其他投资类型"),
            ]
            for cat_name, cat_desc in default_categories:
                if self.db_type == "postgresql":
                    cursor.execute(
                        """
                        INSERT INTO categories (name, description)
                        VALUES (%s, %s)
                        ON CONFLICT (name) DO NOTHING
                        """,
                        (cat_name, cat_desc),
                    )
                else:
                    cursor.execute(
                        "INSERT INTO categories (name, description) VALUES (?, ?)",
                        (cat_name, cat_desc),
                    )

            self.conn.commit()

            # 清除内存中的库存缓存
            self.analytics._rebuild_all_inventory()
            clear_related_cache()

            logging.info("数据库已清空并重新初始化默认数据")
            return True
        except Exception as e:
            logging.error(f"清空数据库失败: {e}", exc_info=True)
            self.conn.rollback()
            return False

    def close(self):
        """关闭数据库连接"""
        self.db_manager.close()
