"""
交易业务操作层 - CRUD Transactions
专门负责买入、卖出、分红等交易的增删改查操作
"""

import sqlite3
import pandas as pd
from typing import Optional, Dict
from datetime import datetime, timedelta
import logging

from utils.db_sqlite_manager import SQLiteManager
from return_rate_sqlite import generate_return_rate


class TransactionCRUD:
    """交易业务操作类"""

    def __init__(self, db_manager: SQLiteManager):
        """初始化交易业务操作类

        Args:
            db_manager: SQLiteManager 实例，提供数据库连接
        """
        self.db_manager = db_manager

    @property
    def conn(self) -> sqlite3.Connection:
        """获取数据库连接"""
        return self.db_manager.get_connection()

    def add_transaction(self, transaction: Dict, analytics) -> bool:
        """添加交易记录（买入、卖出、分红等）

        Args:
            transaction: 交易记录字典，包含以下字段：
                - ledger_id: 账本ID
                - account_id: 账户ID
                - date: 交易日期
                - type: 交易类型（买入、卖出、分红等）
                - category: 投资类别名称或 category_id
                - code: 证券代码
                - name: 证券名称
                - quantity: 数量
                - price: 价格
                - currency: 币种代码或 currency_id
                - amount: 金额
                - fee: 手续费
                - notes: 备注
            analytics: Analytics 实例，用于更新持仓

        Returns:
            bool: 是否成功
        """
        try:
            cursor = self.conn.cursor()
            # 解析 category/currency 为 id（支持传入 name/code 或 id）
            cat = transaction.get("category")
            if isinstance(cat, int) or (isinstance(cat, str) and (cat or "").isdigit()):
                category_id = int(cat or 0)
            else:
                cursor.execute(
                    "SELECT id FROM categories WHERE name = ? LIMIT 1", (cat or "",)
                )
                r = cursor.fetchone()
                category_id = r[0] if r else None
            # 未传或未匹配到类别时：优先使用「其他」，否则使用第一个类别
            if category_id is None:
                cursor.execute(
                    "SELECT id FROM categories WHERE name = ? LIMIT 1", ("其他",)
                )
                r = cursor.fetchone()
                category_id = r[0] if r else None
            if category_id is None:
                cursor.execute("SELECT id FROM categories ORDER BY id LIMIT 1")
                r = cursor.fetchone()
                category_id = r[0] if r else None
            if category_id is None:
                logging.warning(
                    "无法解析 category 为有效 id（未提供且数据库中无投资类别），添加交易失败"
                )
                return False

            curr = transaction.get("currency", "CNY")
            if isinstance(curr, int) or (
                isinstance(curr, str) and (curr or "").isdigit()
            ):
                currency_id = int(curr or 0)
            else:
                code = (curr or "CNY").strip() or "CNY"
                cursor.execute(
                    "SELECT id FROM currencies WHERE code = ? LIMIT 1", (code,)
                )
                r = cursor.fetchone()
                currency_id = r[0] if r else None
                # 币种不存在时由各数据库管理器按设置中的默认汇率插入（SQLite/PostgreSQL/D1 均支持）
                if currency_id is None and code:
                    ensure = getattr(
                        self.db_manager, "ensure_currency_exists", None
                    )
                    if callable(ensure):
                        ensure(code)
                    cursor.execute(
                        "SELECT id FROM currencies WHERE code = ? LIMIT 1",
                        (code.upper(),),
                    )
                    r = cursor.fetchone()
                    currency_id = r[0] if r else None
            if currency_id is None:
                logging.warning(
                    "无法解析 currency 为有效 id（币种 %s 不存在），添加交易失败",
                    curr,
                )
                return False
            currency_code = (
                curr if isinstance(curr, str) and not (curr or "").isdigit() else None
            )
            if not currency_code:
                cursor.execute(
                    "SELECT code FROM currencies WHERE id = ?", (currency_id,)
                )
                row = cursor.fetchone()
                currency_code = row[0] if row else "CNY"
            trans_date = transaction.get("date")
            if trans_date:
                amount_cny = analytics.convert_to_cny_at_date(
                    transaction["amount"], currency_code, trans_date
                )
            else:
                amount_cny = analytics.convert_to_cny(
                    transaction["amount"], currency_code
                )

            cursor.execute(
                """
                INSERT INTO transactions (ledger_id, account_id, date, type, category_id, code, name,
                                         quantity, price, currency_id, amount, amount_cny, fee, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    transaction["ledger_id"],
                    transaction["account_id"],
                    transaction["date"],
                    transaction["type"],
                    category_id,
                    transaction["code"],
                    transaction["name"],
                    transaction["quantity"],
                    transaction["price"],
                    currency_id,
                    transaction["amount"],
                    amount_cny,
                    transaction.get("fee", 0),
                    transaction.get("notes", ""),
                ),
            )

            # 获取刚插入的交易ID
            transaction_id = cursor.lastrowid

            # 自动创建关联资金记录（与交易一对一，删除时一并删除）
            trans_type = transaction.get("type")
            if trans_type in ("买入", "卖出", "开仓", "平仓", "分红"):
                cursor.execute(
                    """
                    INSERT INTO fund_transactions (
                        ledger_id, date, type, currency_id, notes, transaction_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                """,
                    (
                        transaction["ledger_id"],
                        transaction["date"],
                        trans_type,
                        currency_id,
                        transaction.get("notes"),
                        transaction_id,
                    ),
                )
                fund_transaction_id = cursor.lastrowid
                account_id = transaction["account_id"]
                amount = transaction["amount"]
                if trans_date:
                    amount_cny_entry = analytics.convert_to_cny_at_date(
                        amount, currency_code, trans_date
                    )
                else:
                    amount_cny_entry = analytics.convert_to_cny(
                        amount, currency_code
                    )
                # 买入/开仓：借-持仓(增)、贷-现金(减)；卖出/平仓/分红：借-现金(增)、贷-持仓(减)
                if trans_type in ("买入", "开仓"):
                    entries = [
                        {
                            "account_id": account_id,
                            "side": "debit",
                            "amount": amount,
                            "subject_type": "position",
                        },
                        {
                            "account_id": account_id,
                            "side": "credit",
                            "amount": amount,
                            "subject_type": "cash",
                        },
                    ]
                else:
                    entries = [
                        {
                            "account_id": account_id,
                            "side": "debit",
                            "amount": amount,
                            "subject_type": "cash",
                        },
                        {
                            "account_id": account_id,
                            "side": "credit",
                            "amount": amount,
                            "subject_type": "position",
                        },
                    ]
                for entry in entries:
                    cursor.execute(
                        """
                        INSERT INTO fund_transaction_entries
                        (fund_transaction_id, account_id, side, amount, amount_cny, subject_type)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """,
                        (
                            fund_transaction_id,
                            entry["account_id"],
                            entry["side"],
                            entry["amount"],
                            amount_cny_entry,
                            entry.get("subject_type", "cash"),
                        ),
                    )

            # 更新持仓（通过 analytics 模块）
            analytics.update_position(transaction, transaction_id)

            self.conn.commit()
            return True
        except Exception as e:
            logging.error(f"添加交易记录失败: {e}")
            self.conn.rollback()
            return False

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
        """获取交易记录

        Args:
            ledger_id: 账本ID（可选）
            account_id: 账户ID（可选）
            trans_type: 交易类型（可选）
            category: 投资类别（可选）
            start_date: 开始日期（可选）
            end_date: 结束日期（可选）
            limit: 限制返回数量（可选）
            offset: 偏移量，用于分页（可选）

        Returns:
            pd.DataFrame: 交易记录数据框
        """
        query = """
            SELECT t.*, l.name as ledger_name, a.name as account_name,
                   c.code as currency, c.symbol as currency_symbol,
                   cat.name as category
            FROM transactions t
            LEFT JOIN ledgers l ON t.ledger_id = l.id
            LEFT JOIN accounts a ON t.account_id = a.id
            LEFT JOIN currencies c ON t.currency_id = c.id
            LEFT JOIN categories cat ON t.category_id = cat.id
            WHERE 1=1
        """
        params = []

        if ledger_id:
            query += " AND t.ledger_id = ?"
            params.append(ledger_id)

        if account_id:
            query += " AND t.account_id = ?"
            params.append(account_id)

        if trans_type:
            query += " AND t.type = ?"
            params.append(trans_type)

        if category:
            query += " AND t.category_id = (SELECT id FROM categories WHERE name = ? LIMIT 1)"
            params.append(category)

        if start_date:
            query += " AND t.date >= ?"
            params.append(start_date)

        if end_date:
            query += " AND t.date <= ?"
            params.append(end_date)

        query += " ORDER BY t.date DESC, t.id DESC"

        if limit:
            query += f" LIMIT {limit}"
            if offset is not None:
                query += f" OFFSET {offset}"

        df = pd.read_sql_query(query, self.conn, params=params)
        return df

    def get_transactions_count(
        self,
        ledger_id: Optional[int] = None,
        account_id: Optional[int] = None,
        trans_type: Optional[str] = None,
        category: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> int:
        """获取交易记录总数（用于分页）

        Args:
            ledger_id: 账本ID（可选）
            account_id: 账户ID（可选）
            trans_type: 交易类型（可选）
            category: 投资类别（可选）
            start_date: 开始日期（可选）
            end_date: 结束日期（可选）

        Returns:
            int: 符合条件的交易记录总数
        """
        query = """
            SELECT COUNT(*) as count
            FROM transactions t
            WHERE 1=1
        """
        params = []

        if ledger_id:
            query += " AND t.ledger_id = ?"
            params.append(ledger_id)

        if account_id:
            query += " AND t.account_id = ?"
            params.append(account_id)

        if trans_type:
            query += " AND t.type = ?"
            params.append(trans_type)

        if category:
            query += " AND t.category_id = (SELECT id FROM categories WHERE name = ? LIMIT 1)"
            params.append(category)

        if start_date:
            query += " AND t.date >= ?"
            params.append(start_date)

        if end_date:
            query += " AND t.date <= ?"
            params.append(end_date)

        try:
            cursor = self.conn.cursor()
            cursor.execute(query, params)
            result = cursor.fetchone()
            return result[0] if result else 0
        except Exception as e:
            logging.error(f"获取交易记录总数失败: {e}")
            return 0

    def get_transaction_by_id(self, transaction_id: int) -> Optional[Dict]:
        """根据ID获取单条交易记录

        Args:
            transaction_id: 交易记录ID

        Returns:
            Dict: 交易记录字典，如果不存在则返回 None
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT t.*, l.name as ledger_name, a.name as account_name,
                       c.code as currency, cat.name as category
                FROM transactions t
                LEFT JOIN ledgers l ON t.ledger_id = l.id
                LEFT JOIN accounts a ON t.account_id = a.id
                LEFT JOIN currencies c ON t.currency_id = c.id
                LEFT JOIN categories cat ON t.category_id = cat.id
                WHERE t.id = ?
            """,
                (transaction_id,),
            )
            row = cursor.fetchone()
            if row:
                columns = [description[0] for description in cursor.description]
                return dict(zip(columns, row))
            return None
        except Exception as e:
            logging.error(f"获取交易记录失败: {e}")
            return None

    def update_transaction(
        self, transaction_id: int, transaction: Dict, analytics
    ) -> bool:
        """更新交易记录

        Args:
            transaction_id: 交易记录ID
            transaction: 交易记录字典
            analytics: Analytics 实例，用于更新持仓

        Returns:
            bool: 是否成功
        """
        try:
            cursor = self.conn.cursor()
            cat = transaction.get("category")
            if isinstance(cat, int) or (isinstance(cat, str) and (cat or "").isdigit()):
                category_id = int(cat or 0)
            else:
                cursor.execute(
                    "SELECT id FROM categories WHERE name = ? LIMIT 1", (cat or "",)
                )
                r = cursor.fetchone()
                category_id = r[0] if r else None
            if category_id is None:
                cursor.execute(
                    "SELECT id FROM categories WHERE name = ? LIMIT 1", ("其他",)
                )
                r = cursor.fetchone()
                category_id = r[0] if r else None
            if category_id is None:
                cursor.execute("SELECT id FROM categories ORDER BY id LIMIT 1")
                r = cursor.fetchone()
                category_id = r[0] if r else None
            if category_id is None:
                logging.warning(
                    "无法解析 category 为有效 id（未提供且数据库中无投资类别），更新交易失败"
                )
                return False

            curr = transaction.get("currency", "CNY")
            if isinstance(curr, int) or (
                isinstance(curr, str) and (curr or "").isdigit()
            ):
                currency_id = int(curr or 0)
            else:
                code = (curr or "CNY").strip() or "CNY"
                cursor.execute(
                    "SELECT id FROM currencies WHERE code = ? LIMIT 1", (code,)
                )
                r = cursor.fetchone()
                currency_id = r[0] if r else None
                if currency_id is None and code:
                    ensure = getattr(
                        self.db_manager, "ensure_currency_exists", None
                    )
                    if callable(ensure):
                        ensure(code)
                    cursor.execute(
                        "SELECT id FROM currencies WHERE code = ? LIMIT 1",
                        (code.upper(),),
                    )
                    r = cursor.fetchone()
                    currency_id = r[0] if r else None
            if currency_id is None:
                logging.warning(
                    "无法解析 currency 为有效 id（币种 %s 不存在），更新交易失败",
                    curr,
                )
                return False
            currency_code = (
                curr if isinstance(curr, str) and not (curr or "").isdigit() else None
            )
            if not currency_code:
                cursor.execute(
                    "SELECT code FROM currencies WHERE id = ?", (currency_id,)
                )
                row = cursor.fetchone()
                currency_code = row[0] if row else "CNY"
            trans_date = transaction.get("date")
            if trans_date:
                amount_cny = analytics.convert_to_cny_at_date(
                    transaction["amount"], currency_code, trans_date
                )
            else:
                amount_cny = analytics.convert_to_cny(
                    transaction["amount"], currency_code
                )

            cursor.execute(
                """
                UPDATE transactions
                SET ledger_id = ?, account_id = ?, date = ?, type = ?, category_id = ?,
                    code = ?, name = ?, quantity = ?, price = ?, currency_id = ?,
                    amount = ?, amount_cny = ?, fee = ?, notes = ?
                WHERE id = ?
            """,
                (
                    transaction["ledger_id"],
                    transaction["account_id"],
                    transaction["date"],
                    transaction["type"],
                    category_id,
                    transaction["code"],
                    transaction["name"],
                    transaction["quantity"],
                    transaction["price"],
                    currency_id,
                    transaction["amount"],
                    amount_cny,
                    transaction.get("fee", 0),
                    transaction.get("notes", ""),
                    transaction_id,
                ),
            )

            self.conn.commit()

            # 重新同步所有持仓
            analytics.rebuild_all_positions()

            return True
        except Exception as e:
            logging.error(f"更新交易记录失败: {e}")
            self.conn.rollback()
            return False

    def _delete_position_history_for_transaction(
        self, cursor, transaction_id: int
    ) -> None:
        """删除与某笔交易相关的持仓历史记录。该交易影响的 (ledger_id, account_id, code) 从交易日期起的历史快照需失效。"""
        cursor.execute(
            "SELECT ledger_id, account_id, code, date FROM transactions WHERE id = ?",
            (transaction_id,),
        )
        row = cursor.fetchone()
        if not row:
            return
        ledger_id, account_id, code, trans_date = row
        cursor.execute(
            """
            DELETE FROM position_history
            WHERE ledger_id = ? AND account_id = ? AND code = ? AND date >= ?
        """,
            (ledger_id, account_id, code, trans_date),
        )

    def delete_transaction(
        self, transaction_id: int, analytics, db=None, rebuild_positions: bool = True
    ) -> bool:
        """删除交易记录并重新同步持仓。若该交易有关联的资金明细（与 transaction_id 关联），则一并删除。
        同时删除对应的持仓历史（position_history）中受影响的记录，并重新生成。

        Args:
            transaction_id: 交易记录ID
            analytics: Analytics 实例，用于重新同步持仓
            db: Database 实例，用于重新生成持仓历史（可选）
            rebuild_positions: 是否重新同步持仓，默认为True。批量删除时可以设为False，最后统一重建

        Returns:
            bool: 是否成功
        """
        try:
            cursor = self.conn.cursor()
            # 先获取交易信息（需在删除前）
            cursor.execute(
                "SELECT ledger_id, account_id, code, date FROM transactions WHERE id = ?",
                (transaction_id,),
            )
            row = cursor.fetchone()
            if not row:
                return False
            ledger_id, account_id, code, trans_date = row
            trans_date_str = (
                trans_date.strftime("%Y-%m-%d")
                if isinstance(trans_date, datetime)
                else str(trans_date)
            )

            # 删除受影响的持仓历史（从交易日期开始）
            self._delete_position_history_for_transaction(cursor, transaction_id)

            # 删除关联的资金明细
            cursor.execute(
                "DELETE FROM fund_transactions WHERE transaction_id = ?",
                (transaction_id,),
            )
            cursor.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))
            self.conn.commit()

            # 重新同步所有持仓
            if rebuild_positions:
                analytics.rebuild_all_positions()

            # 重新生成持仓历史快照（从交易日期到昨天，不查询价格API）
            if db is not None:
                yesterday = datetime.now() - timedelta(days=1)
                end_date = yesterday.strftime("%Y-%m-%d")
                if trans_date_str <= end_date:
                    db.generate_snapshots_only(
                        trans_date_str, end_date, ledger_id, account_id
                    )

            # 重新计算收益净值表
            try:
                generate_return_rate(
                    self.conn,
                    ledger_id=ledger_id,
                    full_refresh=True,
                    write_to_db=True,
                    db=db,
                )
            except Exception as e:
                logging.error(f"删除交易后重新计算收益净值失败: {e}")

            return True
        except Exception as e:
            logging.error(f"删除交易记录失败: {e}")
            self.conn.rollback()
            return False

    def add_fund_transaction(self, fund_trans: Dict, analytics) -> bool:
        """添加资金明细记录（支持多借多贷）

        Args:
            fund_trans: 资金明细字典，包含以下字段：
                - ledger_id: 账本ID
                - date: 日期
                - type: 类型（本金投入、本金撤出、收入、支出、内转等）
                - currency: 币种
                - notes: 备注
                - entries: 借贷分录列表，每个分录包含：
                    - account_id: 账户ID
                    - side: 借贷方向（'debit' 或 'credit'）
                    - amount: 金额
            analytics: Analytics 实例，用于汇率转换

        Returns:
            bool: 是否成功
        """
        def _resolve_currency(cursor, curr):
            """将 code 或 id 解析为 (currency_id, code)。"""
            if curr is None or curr == "":
                curr = "CNY"
            if isinstance(curr, int) or (
                isinstance(curr, str) and (curr or "").isdigit()
            ):
                cid = int(curr or 0)
                r = cursor.execute(
                    "SELECT id, code FROM currencies WHERE id = ? LIMIT 1", (cid,)
                ).fetchone()
                return (r[0], r[1]) if r else (None, None)
            cursor.execute(
                "SELECT id, code FROM currencies WHERE code = ? LIMIT 1", (curr or "CNY",)
            )
            r = cursor.fetchone()
            return (r[0], r[1]) if r else (None, None)

        try:
            cursor = self.conn.cursor()
            entries = fund_trans.get("entries", [])

            # 主记录 currency_id：有 entries 时用首条分录币种，否则用 fund_trans.currency
            if entries:
                first_curr = entries[0].get("currency", fund_trans.get("currency", "CNY"))
                currency_id, _ = _resolve_currency(cursor, first_curr)
            else:
                currency_id, _ = _resolve_currency(cursor, fund_trans.get("currency", "CNY"))
            if currency_id is None:
                logging.warning("无法解析 currency 为有效 id，添加资金明细失败")
                return False

            # 创建主交易记录
            cursor.execute(
                """
                INSERT INTO fund_transactions (
                    ledger_id, date, type, currency_id, notes
                )
                VALUES (?, ?, ?, ?, ?)
            """,
                (
                    fund_trans["ledger_id"],
                    fund_trans["date"],
                    fund_trans["type"],
                    currency_id,
                    fund_trans.get("notes"),
                ),
            )

            transaction_id = cursor.lastrowid

            # 添加借贷分录明细
            if not entries:
                # 兼容旧格式：如果没有entries，尝试从旧字段创建
                if "debit_account" in fund_trans or "credit_account" in fund_trans:
                    # 旧格式，需要迁移
                    amount = fund_trans.get("amount", 0)
                    curr = fund_trans.get("currency", "CNY")
                    curr_code = (
                        curr
                        if isinstance(curr, str)
                        else (
                            cursor.execute(
                                "SELECT code FROM currencies WHERE id=?", (curr,)
                            ).fetchone()
                            or ("CNY",)
                        )[0]
                    )
                    fund_date = fund_trans.get("date")
                    if fund_date:
                        amount_cny = analytics.convert_to_cny_at_date(
                            amount, curr_code, fund_date
                        )
                    else:
                        amount_cny = analytics.convert_to_cny(amount, curr_code)

                    # 旧格式：分录使用主记录同一币种
                    ent_currency_id = currency_id
                    if fund_trans.get("account_id"):
                        cursor.execute(
                            """
                            INSERT INTO fund_transaction_entries 
                            (fund_transaction_id, account_id, side, amount, amount_cny, currency_id, subject_type)
                            VALUES (?, ?, 'debit', ?, ?, ?, 'cash')
                        """,
                            (
                                transaction_id,
                                fund_trans["account_id"],
                                amount,
                                amount_cny,
                                ent_currency_id,
                            ),
                        )

                    if fund_trans.get("target_account_id"):
                        cursor.execute(
                            """
                            INSERT INTO fund_transaction_entries 
                            (fund_transaction_id, account_id, side, amount, amount_cny, currency_id, subject_type)
                            VALUES (?, ?, 'credit', ?, ?, ?, 'cash')
                        """,
                            (
                                transaction_id,
                                fund_trans["target_account_id"],
                                amount,
                                amount_cny,
                                ent_currency_id,
                            ),
                        )
                    elif fund_trans.get("account_id"):
                        cursor.execute(
                            """
                            INSERT INTO fund_transaction_entries 
                            (fund_transaction_id, account_id, side, amount, amount_cny, currency_id, subject_type)
                            VALUES (?, ?, 'credit', ?, ?, ?, 'cash')
                        """,
                            (
                                transaction_id,
                                fund_trans["account_id"],
                                amount,
                                amount_cny,
                                ent_currency_id,
                            ),
                        )
                else:
                    raise ValueError("必须提供 entries 或兼容的旧格式字段")
            else:
                # 多借多贷：每笔分录可有独立币种，按人民币折算后校验借贷平衡
                fund_date = fund_trans.get("date")
                debit_cny = 0.0
                credit_cny = 0.0
                entries_with_cny = []
                for entry in entries:
                    entry_curr = entry.get("currency", fund_trans.get("currency", "CNY"))
                    ent_currency_id, curr_code = _resolve_currency(cursor, entry_curr)
                    if ent_currency_id is None:
                        raise ValueError(f"分录币种无法解析: {entry_curr}")
                    amount = entry["amount"]
                    if fund_date:
                        amount_cny = analytics.convert_to_cny_at_date(
                            amount, curr_code, fund_date
                        )
                    else:
                        amount_cny = analytics.convert_to_cny(amount, curr_code)
                    if entry["side"] == "debit":
                        debit_cny += amount_cny
                    else:
                        credit_cny += amount_cny
                    entries_with_cny.append(
                        (entry["account_id"], entry["side"], amount, amount_cny, entry.get("subject_type", "cash"), ent_currency_id)
                    )

                if abs(debit_cny - credit_cny) > 0.01:
                    raise ValueError(
                        f"借贷不平衡（按人民币折算）：借方 {debit_cny:.2f}，贷方 {credit_cny:.2f}"
                    )

                for account_id, side, amount, amount_cny, subject_type, ent_currency_id in entries_with_cny:
                    cursor.execute(
                        """
                        INSERT INTO fund_transaction_entries 
                        (fund_transaction_id, account_id, side, amount, amount_cny, currency_id, subject_type)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            transaction_id,
                            account_id,
                            side,
                            amount,
                            amount_cny,
                            ent_currency_id,
                            subject_type,
                        ),
                    )

            self.conn.commit()
            return True
        except Exception as e:
            logging.error(f"添加资金明细失败: {e}")
            import traceback

            traceback.print_exc()
            self.conn.rollback()
            return False

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
        """获取资金明细记录（支持多借多贷）

        Args:
            ledger_id: 账本ID（可选）
            account_id: 账户ID（可选）
            trans_type: 交易类型（可选）
            start_date: 开始日期（可选）
            end_date: 结束日期（可选）
            limit: 限制返回数量（可选）
            offset: 偏移量，用于分页（可选）

        Returns:
            pd.DataFrame: 资金明细数据框
        """
        # 借贷记账法：借方/贷方展示为「账户-子科目(持仓/现金) 金额」，持仓与现金为账户下子科目
        query = """
            SELECT 
                ft.id,
                ft.ledger_id,
                ft.date,
                ft.type,
                c.code as currency,
                ft.notes,
                ft.created_at,
                l.name as ledger_name,
                c.symbol as currency_symbol,
                COALESCE((
                    SELECT GROUP_CONCAT(
                        a.name || '-' || (CASE WHEN COALESCE(fte.subject_type,'cash')='position' THEN '持仓' ELSE '现金' END) || ' ' || fte.amount,
                        '; '
                    )
                    FROM fund_transaction_entries fte
                    LEFT JOIN accounts a ON fte.account_id = a.id
                    WHERE fte.fund_transaction_id = ft.id AND fte.side = 'debit'
                ), '') as debit_display,
                COALESCE((
                    SELECT GROUP_CONCAT(
                        a.name || '-' || (CASE WHEN COALESCE(fte.subject_type,'cash')='position' THEN '持仓' ELSE '现金' END) || ' ' || fte.amount,
                        '; '
                    )
                    FROM fund_transaction_entries fte
                    LEFT JOIN accounts a ON fte.account_id = a.id
                    WHERE fte.fund_transaction_id = ft.id AND fte.side = 'credit'
                ), '') as credit_display,
                COALESCE((
                    SELECT GROUP_CONCAT(a.name || ' (' || fte.amount || ')', '; ')
                    FROM fund_transaction_entries fte
                    LEFT JOIN accounts a ON fte.account_id = a.id
                    WHERE fte.fund_transaction_id = ft.id AND fte.side = 'debit'
                ), '') as debit_accounts,
                COALESCE((
                    SELECT GROUP_CONCAT(a.name || ' (' || fte.amount || ')', '; ')
                    FROM fund_transaction_entries fte
                    LEFT JOIN accounts a ON fte.account_id = a.id
                    WHERE fte.fund_transaction_id = ft.id AND fte.side = 'credit'
                ), '') as credit_accounts,
                COALESCE((
                    SELECT SUM(fte.amount)
                    FROM fund_transaction_entries fte
                    WHERE fte.fund_transaction_id = ft.id AND fte.side = 'debit'
                ), 0) as total_debit,
                COALESCE((
                    SELECT SUM(fte.amount)
                    FROM fund_transaction_entries fte
                    WHERE fte.fund_transaction_id = ft.id AND fte.side = 'credit'
                ), 0) as total_credit,
                COALESCE((
                    SELECT SUM(fte.amount_cny)
                    FROM fund_transaction_entries fte
                    WHERE fte.fund_transaction_id = ft.id AND fte.side = 'debit'
                ), 0) as total_debit_cny,
                COALESCE((
                    SELECT SUM(fte.amount_cny)
                    FROM fund_transaction_entries fte
                    WHERE fte.fund_transaction_id = ft.id AND fte.side = 'credit'
                ), 0) as total_credit_cny
            FROM fund_transactions ft
            LEFT JOIN ledgers l ON ft.ledger_id = l.id
            LEFT JOIN currencies c ON ft.currency_id = c.id
            WHERE 1=1
        """
        params = []

        if ledger_id:
            query += " AND ft.ledger_id = ?"
            params.append(ledger_id)

        if account_id:
            query += """ AND EXISTS (
                SELECT 1 FROM fund_transaction_entries fte 
                WHERE fte.fund_transaction_id = ft.id AND fte.account_id = ?
            )"""
            params.append(account_id)

        if trans_type:
            query += " AND ft.type = ?"
            params.append(trans_type)

        if start_date:
            query += " AND ft.date >= ?"
            params.append(start_date)

        if end_date:
            query += " AND ft.date <= ?"
            params.append(end_date)

        query += " ORDER BY ft.date DESC, ft.id DESC"

        if limit:
            query += f" LIMIT {limit}"
            if offset is not None:
                query += f" OFFSET {offset}"

        return pd.read_sql_query(query, self.conn, params=params)

    def get_fund_transactions_count(
        self,
        ledger_id: Optional[int] = None,
        account_id: Optional[int] = None,
        trans_type: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> int:
        """获取资金明细记录总数（用于分页）

        Args:
            ledger_id: 账本ID（可选）
            account_id: 账户ID（可选）
            trans_type: 交易类型（可选）
            start_date: 开始日期（可选）
            end_date: 结束日期（可选）

        Returns:
            int: 符合条件的资金明细记录总数
        """
        query = """
            SELECT COUNT(*) as count
            FROM fund_transactions ft
            WHERE 1=1
        """
        params = []

        if ledger_id:
            query += " AND ft.ledger_id = ?"
            params.append(ledger_id)

        if account_id:
            query += """ AND EXISTS (
                SELECT 1 FROM fund_transaction_entries fte 
                WHERE fte.fund_transaction_id = ft.id AND fte.account_id = ?
            )"""
            params.append(account_id)

        if trans_type:
            query += " AND ft.type = ?"
            params.append(trans_type)

        if start_date:
            query += " AND ft.date >= ?"
            params.append(start_date)

        if end_date:
            query += " AND ft.date <= ?"
            params.append(end_date)

        try:
            cursor = self.conn.cursor()
            cursor.execute(query, params)
            result = cursor.fetchone()
            return result[0] if result else 0
        except Exception as e:
            logging.error(f"获取资金明细记录总数失败: {e}")
            return 0

    def get_fund_transaction_by_id(self, fund_trans_id: int) -> Optional[Dict]:
        """根据ID获取单条资金明细记录（包含多借多贷明细）

        Args:
            fund_trans_id: 资金明细ID

        Returns:
            Dict: 资金明细字典，如果不存在则返回 None
        """
        try:
            cursor = self.conn.cursor()
            # 获取主记录
            cursor.execute(
                """
                SELECT ft.*, l.name as ledger_name, c.code as currency, c.symbol as currency_symbol
                FROM fund_transactions ft
                LEFT JOIN ledgers l ON ft.ledger_id = l.id
                LEFT JOIN currencies c ON ft.currency_id = c.id
                WHERE ft.id = ?
            """,
                (fund_trans_id,),
            )
            row = cursor.fetchone()
            if row:
                columns = [description[0] for description in cursor.description]
                result = dict(zip(columns, row))

                # 获取借贷分录明细
                cursor.execute(
                    """
                    SELECT fte.*, a.name as account_name
                    FROM fund_transaction_entries fte
                    LEFT JOIN accounts a ON fte.account_id = a.id
                    WHERE fte.fund_transaction_id = ?
                    ORDER BY fte.side, fte.id
                """,
                    (fund_trans_id,),
                )
                entries = []
                for entry_row in cursor.fetchall():
                    entry_columns = [
                        description[0] for description in cursor.description
                    ]
                    entries.append(dict(zip(entry_columns, entry_row)))

                result["entries"] = entries
                return result
            return None
        except Exception as e:
            logging.error(f"获取资金明细失败: {e}")
            import traceback

            traceback.print_exc()
            return None

    def get_account_transaction_entries(
        self,
        account_id: int,
        trans_type: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> pd.DataFrame:
        """获取指定账户的资金变动明细（基于 fund_transaction_entries）

        每条记录包含该账户在资金交易中的借贷方向和金额。
        debit=借方增加余额，credit=贷方减少余额。

        Args:
            account_id: 账户ID
            trans_type: 交易类型（可选）
            start_date: 开始日期（可选）
            end_date: 结束日期（可选）
            limit: 限制返回数量（可选）
            offset: 偏移量（可选）

        Returns:
            pd.DataFrame: 账户变动明细
        """
        query = """
            SELECT
                ft.id as fund_transaction_id,
                ft.date,
                ft.type,
                ft.notes,
                c.code as currency,
                fte.side,
                fte.amount,
                fte.amount_cny,
                COALESCE(fte.subject_type, 'cash') as subject_type,
                CASE WHEN fte.side = 'debit' THEN fte.amount_cny ELSE -fte.amount_cny END as balance_change_cny,
                CASE WHEN COALESCE(fte.subject_type, 'cash') = 'cash'
                     THEN CASE WHEN fte.side = 'debit' THEN fte.amount_cny ELSE -fte.amount_cny END
                     ELSE 0 END as cash_change_cny,
                (
                    SELECT COALESCE(SUM(
                        CASE WHEN COALESCE(fte2.subject_type, 'cash') = 'cash'
                             THEN CASE WHEN fte2.side = 'debit' THEN fte2.amount_cny ELSE -fte2.amount_cny END
                             ELSE 0 END
                    ), 0)
                    FROM fund_transaction_entries fte2
                    JOIN fund_transactions ft2 ON fte2.fund_transaction_id = ft2.id
                    WHERE fte2.account_id = fte.account_id
                    AND (
                        ft2.date < ft.date
                        OR (ft2.date = ft.date AND ft2.id < ft.id)
                        OR (ft2.date = ft.date AND ft2.id = ft.id AND fte2.id <= fte.id)
                    )
                ) as balance
            FROM fund_transaction_entries fte
            JOIN fund_transactions ft ON fte.fund_transaction_id = ft.id
            LEFT JOIN currencies c ON ft.currency_id = c.id
            WHERE fte.account_id = ?
        """
        params = [account_id]

        if trans_type:
            query += " AND ft.type = ?"
            params.append(trans_type)

        if start_date:
            query += " AND ft.date >= ?"
            params.append(start_date)

        if end_date:
            query += " AND ft.date <= ?"
            params.append(end_date)

        query += " ORDER BY ft.date DESC, ft.id DESC, fte.id DESC"

        if limit:
            query += f" LIMIT {limit}"
            if offset is not None:
                query += f" OFFSET {offset}"

        return pd.read_sql_query(query, self.conn, params=params)

    def get_account_transaction_entries_count(
        self,
        account_id: int,
        trans_type: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> int:
        """获取账户变动明细总数"""
        query = """
            SELECT COUNT(*)
            FROM fund_transaction_entries fte
            JOIN fund_transactions ft ON fte.fund_transaction_id = ft.id
            WHERE fte.account_id = ?
        """
        params = [account_id]

        if trans_type:
            query += " AND ft.type = ?"
            params.append(trans_type)

        if start_date:
            query += " AND ft.date >= ?"
            params.append(start_date)

        if end_date:
            query += " AND ft.date <= ?"
            params.append(end_date)

        try:
            cursor = self.conn.cursor()
            cursor.execute(query, params)
            result = cursor.fetchone()
            return result[0] if result else 0
        except Exception as e:
            logging.error(f"获取账户变动明细总数失败: {e}")
            return 0

    def delete_fund_transaction(self, fund_trans_id: int) -> bool:
        """删除资金明细记录。若该资金明细关联交易记录（开仓/平仓），则一并删除交易及同批其他资金明细。

        Args:
            fund_trans_id: 资金明细ID

        Returns:
            bool: 是否成功
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT transaction_id FROM fund_transactions WHERE id = ?",
                (fund_trans_id,),
            )
            row = cursor.fetchone()
            linked_transaction_id = row[0] if row and row[0] is not None else None
            if linked_transaction_id is not None:
                # 有关联交易：先删除受影响的持仓历史，再删除该交易对应的全部资金明细，最后删交易
                self._delete_position_history_for_transaction(
                    cursor, linked_transaction_id
                )
                cursor.execute(
                    "DELETE FROM fund_transactions WHERE transaction_id = ?",
                    (linked_transaction_id,),
                )
                cursor.execute(
                    "DELETE FROM transactions WHERE id = ?", (linked_transaction_id,)
                )
            else:
                cursor.execute(
                    "DELETE FROM fund_transactions WHERE id = ?", (fund_trans_id,)
                )
            self.conn.commit()
            return True
        except Exception as e:
            logging.error(f"删除资金明细失败: {e}")
            return False

    def add_transaction_with_fund(self, transaction: Dict, analytics) -> bool:
        """添加交易记录并同时记录资金明细（用于开仓/平仓）

        Args:
            transaction: 交易记录字典（含 category/currency 名称或 id）
            analytics: Analytics 实例，用于更新持仓和汇率转换

        Returns:
            bool: 是否成功
        """
        try:
            cursor = self.conn.cursor()
            cat = transaction.get("category")
            if isinstance(cat, int) or (isinstance(cat, str) and (cat or "").isdigit()):
                category_id = int(cat or 0)
            else:
                cursor.execute(
                    "SELECT id FROM categories WHERE name = ? LIMIT 1", (cat or "",)
                )
                r = cursor.fetchone()
                category_id = r[0] if r else None
            if category_id is None:
                cursor.execute(
                    "SELECT id FROM categories WHERE name = ? LIMIT 1", ("其他",)
                )
                r = cursor.fetchone()
                category_id = r[0] if r else None
            if category_id is None:
                cursor.execute("SELECT id FROM categories ORDER BY id LIMIT 1")
                r = cursor.fetchone()
                category_id = r[0] if r else None
            if category_id is None:
                logging.warning(
                    "无法解析 category 为有效 id（未提供且数据库中无投资类别），添加交易及资金明细失败"
                )
                return False

            curr = transaction.get("currency", "CNY")
            if isinstance(curr, int) or (
                isinstance(curr, str) and (curr or "").isdigit()
            ):
                currency_id = int(curr or 0)
            else:
                code = (curr or "CNY").strip() or "CNY"
                cursor.execute(
                    "SELECT id FROM currencies WHERE code = ? LIMIT 1", (code,)
                )
                r = cursor.fetchone()
                currency_id = r[0] if r else None
                if currency_id is None and code:
                    ensure = getattr(
                        self.db_manager, "ensure_currency_exists", None
                    )
                    if callable(ensure):
                        ensure(code)
                    cursor.execute(
                        "SELECT id FROM currencies WHERE code = ? LIMIT 1",
                        (code.upper(),),
                    )
                    r = cursor.fetchone()
                    currency_id = r[0] if r else None
            if currency_id is None:
                logging.warning(
                    "无法解析 currency 为有效 id（币种 %s 不存在），添加交易及资金明细失败",
                    curr,
                )
                return False
            curr_code = (
                curr if isinstance(curr, str) and not (curr or "").isdigit() else None
            )
            if not curr_code:
                cursor.execute(
                    "SELECT code FROM currencies WHERE id = ?", (currency_id,)
                )
                row = cursor.fetchone()
                curr_code = row[0] if row else "CNY"
            trans_date = transaction.get("date")
            if trans_date:
                amount_cny = analytics.convert_to_cny_at_date(
                    transaction["amount"], curr_code, trans_date
                )
            else:
                amount_cny = analytics.convert_to_cny(transaction["amount"], curr_code)

            cursor.execute(
                """
                INSERT INTO transactions (ledger_id, account_id, date, type, category_id, code, name,
                                         quantity, price, currency_id, amount, amount_cny, fee, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    transaction["ledger_id"],
                    transaction["account_id"],
                    transaction["date"],
                    transaction["type"],
                    category_id,
                    transaction["code"],
                    transaction["name"],
                    transaction["quantity"],
                    transaction["price"],
                    currency_id,
                    transaction["amount"],
                    amount_cny,
                    transaction.get("fee", 0),
                    transaction.get("notes", ""),
                ),
            )

            transaction_id = cursor.lastrowid
            analytics.update_position(transaction, transaction_id)

            account_id = transaction["account_id"]
            cursor.execute(
                """
                INSERT INTO fund_transactions (
                    ledger_id, date, type, currency_id, notes, transaction_id
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    transaction["ledger_id"],
                    transaction["date"],
                    transaction["type"],
                    currency_id,
                    transaction.get("notes"),
                    transaction_id,
                ),
            )

            fund_transaction_id = cursor.lastrowid

            # 开仓和平仓的资金变动：在核心层区分持仓与现金
            # 开仓：借-持仓(增)、贷-现金(减)；平仓：借-现金(增)、贷-持仓(减)
            trans_type = transaction["type"]
            if trans_type == "开仓":
                entries = [
                    {
                        "account_id": account_id,
                        "side": "debit",
                        "amount": transaction["amount"],
                        "subject_type": "position",
                    },
                    {
                        "account_id": account_id,
                        "side": "credit",
                        "amount": transaction["amount"],
                        "subject_type": "cash",
                    },
                ]
            else:
                entries = [
                    {
                        "account_id": account_id,
                        "side": "debit",
                        "amount": transaction["amount"],
                        "subject_type": "cash",
                    },
                    {
                        "account_id": account_id,
                        "side": "credit",
                        "amount": transaction["amount"],
                        "subject_type": "position",
                    },
                ]

            trans_date = transaction.get("date")
            for entry in entries:
                amount = entry["amount"]
                if trans_date:
                    amount_cny_entry = analytics.convert_to_cny_at_date(
                        amount, curr_code, trans_date
                    )
                else:
                    amount_cny_entry = analytics.convert_to_cny(amount, curr_code)
                subject_type = entry.get("subject_type", "cash")
                cursor.execute(
                    """
                    INSERT INTO fund_transaction_entries 
                    (fund_transaction_id, account_id, side, amount, amount_cny, subject_type)
                    VALUES (?, ?, ?, ?, ?, ?)
                """,
                    (
                        fund_transaction_id,
                        entry["account_id"],
                        entry["side"],
                        amount,
                        amount_cny_entry,
                        subject_type,
                    ),
                )

            # 手续费已包含在开仓/平仓的 amount 中（开仓：amount=数量*价格+手续费；平仓：amount=数量*价格-手续费），
            # 无需额外创建支出类型的资金明细，否则会重复记账

            self.conn.commit()
            return True
        except Exception as e:
            logging.error(f"添加交易及资金明细失败: {e}")
            self.conn.rollback()
            return False
