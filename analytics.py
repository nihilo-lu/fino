"""
逻辑计算层 - Analytics
专门负责计算收益率、持仓成本、资产占比等逻辑计算
"""

import sqlite3
import pandas as pd
from typing import Optional, Dict, List
from decimal import Decimal
import logging

from utils.db_sqlite_manager import SQLiteManager
from utils.fifo_framework import FIFOInventory
from utils.wac_framework import WACInventory

# 成本计算方法常量
COST_METHOD_FIFO = "FIFO"  # 先进先出法
COST_METHOD_WAC = "WAC"  # 加权平均成本法
DEFAULT_COST_METHOD = COST_METHOD_FIFO


class Analytics:
    """逻辑计算类 - 负责收益率、持仓成本、资产占比等计算"""

    _initial_load_complete = False

    def __init__(self, db_manager: SQLiteManager):
        """初始化逻辑计算类

        Args:
            db_manager: SQLiteManager 实例，提供数据库连接
        """
        self.db_manager = db_manager

        self.fifo_inventory: Optional[FIFOInventory] = None
        self.wac_inventory: Optional[WACInventory] = None
        self._ledger_cost_methods: Dict[int, str] = {}
        self._last_processed_ids: Dict[int, int] = {}
        self._init_inventory_managers()

    @property
    def conn(self) -> sqlite3.Connection:
        """获取数据库连接"""
        return self.db_manager.get_connection()

    def _init_inventory_managers(self):
        """初始化库存管理器，只初始化账本实际使用的方法"""
        self._load_ledger_cost_methods()

        used_methods = set(self._ledger_cost_methods.values())

        try:
            if COST_METHOD_FIFO in used_methods:
                self.fifo_inventory = FIFOInventory(enable_exchange_rate=True)
                logging.info("已初始化 FIFO 库存管理器")

            if COST_METHOD_WAC in used_methods:
                self.wac_inventory = WACInventory(enable_exchange_rate=True)
                logging.info("已初始化 WAC 库存管理器（加权平均成本法）")

            self._rebuild_all_inventory()
            Analytics._initial_load_complete = True
            logging.info("库存管理器初始化成功")
        except Exception as e:
            logging.error(f"库存管理器初始化失败: {e}")
            self.fifo_inventory = (
                FIFOInventory(enable_exchange_rate=True)
                if COST_METHOD_FIFO in used_methods
                else None
            )
            self.wac_inventory = (
                WACInventory(enable_exchange_rate=True)
                if COST_METHOD_WAC in used_methods
                else None
            )

    def _load_ledger_cost_methods(self):
        """加载所有账本的成本计算方法到缓存"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, cost_method FROM ledgers")
        rows = cursor.fetchall()
        self._ledger_cost_methods = {
            row[0]: row[1] if row[1] else DEFAULT_COST_METHOD for row in rows
        }
        self._load_inventory_state()

    def _load_inventory_state(self):
        """从数据库加载库存计算状态，用于增量计算"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT ledger_id, last_transaction_id FROM inventory_state")
        rows = cursor.fetchall()
        if rows:
            self._last_processed_ids = {row[0]: row[1] for row in rows}
            logging.info(f"已加载库存计算状态: {len(rows)} 个账本")
        else:
            self._last_processed_ids = {}
            logging.info("未找到库存计算状态，将进行全量计算")

    def _save_inventory_state(self, ledger_id: int):
        """保存单个账本的库存计算状态"""
        cursor = self.conn.cursor()
        last_id = self._last_processed_ids.get(ledger_id, 0)
        cursor.execute(
            """
            INSERT OR REPLACE INTO inventory_state (ledger_id, last_transaction_id, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
        """,
            (ledger_id, last_id),
        )

    def get_ledger_cost_method(self, ledger_id: int) -> str:
        """获取账本的成本计算方法

        Args:
            ledger_id: 账本ID

        Returns:
            str: 成本计算方法（FIFO 或 WAC）
        """
        if ledger_id in self._ledger_cost_methods:
            return self._ledger_cost_methods[ledger_id]

        cursor = self.conn.cursor()
        cursor.execute("SELECT cost_method FROM ledgers WHERE id = ?", (ledger_id,))
        row = cursor.fetchone()
        cost_method = row[0] if row and row[0] else DEFAULT_COST_METHOD
        self._ledger_cost_methods[ledger_id] = cost_method
        return cost_method

    def _get_inventory_manager(self, ledger_id: int):
        """根据账本的成本计算方法获取对应的库存管理器

        Args:
            ledger_id: 账本ID

        Returns:
            FIFOInventory 或 WACInventory: 对应的库存管理器
        """
        cost_method = self.get_ledger_cost_method(ledger_id)
        if cost_method == COST_METHOD_WAC:
            return self.wac_inventory
        return self.fifo_inventory  # 默认使用 FIFO

    def _rebuild_all_inventory(self, force_full: bool = False):
        """从交易记录重建所有库存（只重建账本实际使用的方法）

        支持按账本隔离的增量计算：
        - 首次启动或 force_full=True 时：全量重建所有账本
        - 后续调用时（类级别 _initial_load_complete=True）：跳过，避免重复计算

        Args:
            force_full: 是否强制全量重建（用于手动刷新场景）
        """
        if Analytics._initial_load_complete and not force_full:
            logging.info("库存管理器已初始化，跳过重复计算")
            return

        if force_full:
            if self.fifo_inventory:
                self.fifo_inventory.clear_inventory()

            if self.wac_inventory:
                self.wac_inventory.clear_inventory()

            self._last_processed_ids.clear()

        ledgers_df = self.get_ledgers()
        if ledgers_df.empty:
            return

        for _, ledger_row in ledgers_df.iterrows():
            ledger_id = int(ledger_row["id"])
            self._rebuild_ledger_inventory(ledger_id, force_full)

    def _rebuild_ledger_inventory(self, ledger_id: int, force_full: bool = False):
        """按账本重建库存

        Args:
            ledger_id: 账本ID
            force_full: 是否强制全量重建
        """
        last_id = self._last_processed_ids.get(ledger_id, 0)

        if force_full:
            last_id = 0
            self._last_processed_ids[ledger_id] = 0

        if last_id == 0 and not force_full:
            self._rebuild_ledger_inventory(ledger_id, force_full=True)
            return

        query = """
            SELECT
                t.id as 编号,
                t.date as 日期,
                t.code as 代码,
                t.name as 名称,
                t.ledger_id as 账本ID,
                CASE
                    WHEN t.type IN ('买入', '开仓') THEN t.quantity
                    WHEN t.type IN ('卖出', '平仓') THEN -t.quantity
                END as 数量,
                CASE
                    WHEN t.type IN ('买入', '开仓') THEN -t.amount
                    WHEN t.type IN ('卖出', '平仓') THEN t.amount
                END as 金额,
                a.name as 账户,
                c.code as 币种,
                c.exchange_rate as 汇率
            FROM transactions t
            LEFT JOIN accounts a ON t.account_id = a.id
            LEFT JOIN currencies c ON t.currency_id = c.id
            WHERE t.type IN ('买入', '卖出', '开仓', '平仓')
              AND t.ledger_id = ?
        """
        params: list = [ledger_id]

        if last_id > 0:
            query += " AND t.id > ?"
            params.append(last_id)

        query += " ORDER BY t.date, t.id"

        df = pd.read_sql_query(query, self.conn, params=params)

        if not df.empty:
            df = self._prepare_transaction_df(df)
            cost_method = self.get_ledger_cost_method(ledger_id)

            if cost_method == COST_METHOD_FIFO and self.fifo_inventory:
                self.fifo_inventory.add_stock_from_df(df)
                logging.info(
                    f"账本 {ledger_id} FIFO 增量更新完成，新增 {len(df)} 条交易记录"
                )
            elif cost_method == COST_METHOD_WAC and self.wac_inventory:
                self.wac_inventory.add_stock_from_df(df)
                logging.info(
                    f"账本 {ledger_id} WAC 增量更新完成，新增 {len(df)} 条交易记录"
                )

            self._last_processed_ids[ledger_id] = int(df["编号"].max())
            self._save_inventory_state(ledger_id)
            self.conn.commit()

    def _incremental_update_inventory(self):
        """增量更新库存（仅处理新增交易，按账本隔离）"""
        ledgers_df = self.get_ledgers()
        if ledgers_df.empty:
            return

        for _, ledger_row in ledgers_df.iterrows():
            ledger_id = int(ledger_row["id"])
            self._rebuild_ledger_inventory(ledger_id)

    def _prepare_transaction_df(self, df: pd.DataFrame) -> pd.DataFrame:
        """预处理交易记录 DataFrame（填充汇率等）

        Args:
            df: 原始交易记录 DataFrame

        Returns:
            pd.DataFrame: 预处理后的 DataFrame
        """
        if df.empty:
            return df

        if "汇率" not in df.columns or df["汇率"].isna().all():
            df["汇率"] = 1.0
        df["汇率"] = df["汇率"].fillna(1.0)

        for i, row in df.iterrows():
            curr = str(row.get("币种", "CNY"))
            if curr != "CNY":
                hist_rate = self.get_latest_rate_before_date(curr, str(row["日期"]))
                if hist_rate is not None:
                    df.at[i, "汇率"] = hist_rate

        return df

    def update_position(self, transaction: Dict, transaction_id: int):
        """使用 FIFO 或 WAC 框架更新持仓信息（根据账本设置）

        Args:
            transaction: 交易记录字典
            transaction_id: 交易记录ID
        """
        cursor = self.conn.cursor()

        # 获取账户名称
        cursor.execute(
            "SELECT name FROM accounts WHERE id = ?", (transaction["account_id"],)
        )
        account_row = cursor.fetchone()
        account_name = (
            account_row[0] if account_row else f"账户{transaction['account_id']}"
        )

        # 获取汇率
        exchange_rate = self.get_exchange_rate(transaction["currency"])

        # 构建库存管理器所需的 DataFrame 行
        ledger_id = transaction["ledger_id"]
        inventory_row = pd.Series(
            {
                "编号": transaction_id,
                "日期": transaction["date"],
                "代码": transaction["code"],
                "名称": transaction["name"],
                "数量": transaction["quantity"]
                if transaction["type"] in ["买入", "开仓"]
                else -transaction["quantity"],
                "金额": -transaction["amount"]
                if transaction["type"] in ["买入", "开仓"]
                else transaction["amount"],
                "账户": account_name,
                "账本ID": ledger_id,
                "币种": transaction["currency"],
                "汇率": Decimal(str(exchange_rate)),
            }
        )

        # 确保库存管理器已初始化
        if self.fifo_inventory is None:
            self.fifo_inventory = FIFOInventory(enable_exchange_rate=True)
        if self.wac_inventory is None:
            self.wac_inventory = WACInventory(enable_exchange_rate=True)

        ledger_id = transaction["ledger_id"]
        # 确保 ledger_id 存在于 _last_processed_ids 中（用于判断库存是否完整）
        if ledger_id not in self._last_processed_ids:
            cursor.execute(
                "SELECT last_transaction_id FROM inventory_state WHERE ledger_id = ?",
                (ledger_id,),
            )
            row = cursor.fetchone()
            if row:
                self._last_processed_ids[ledger_id] = row[0]
            else:
                self._last_processed_ids[ledger_id] = 0

        last_processed = self._last_processed_ids.get(ledger_id, 0)
        # 若该账本库存可能不完整（如多进程、重启后或首次加仓），先全量重建再同步，避免股数只显示最后一笔
        if last_processed < transaction_id - 1:
            self._rebuild_ledger_inventory(ledger_id, force_full=True)
        else:
            # 增量：仅把当前交易加入库存
            self.fifo_inventory._process_single_transaction(inventory_row, ledger_id)
            self.wac_inventory._process_single_transaction(inventory_row, ledger_id)
            if transaction_id > last_processed:
                self._last_processed_ids[ledger_id] = transaction_id
                self._save_inventory_state(ledger_id)

        # 根据账本设置从对应的库存获取数据并更新数据库
        self._sync_position_from_inventory(transaction, account_name)

    def _sync_position_from_inventory(self, transaction: Dict, account_name: str):
        """从库存管理器同步持仓到数据库（根据账本的成本计算方法）

        Args:
            transaction: 交易记录字典
            account_name: 账户名称
        """
        cursor = self.conn.cursor()
        code = transaction["code"]

        # 获取对应的库存管理器
        inventory_manager = self._get_inventory_manager(transaction["ledger_id"])

        # 获取该代码在该账户的库存
        inventory_list = inventory_manager.get_inventory_list(
            transaction["ledger_id"], code
        )

        # 筛选出该账户的库存记录
        account_inventory = [
            inv for inv in inventory_list if inv["账户"] == account_name
        ]

        # 计算总数量和总成本
        total_quantity = sum(float(inv["数量"]) for inv in account_inventory)
        total_cost = sum(float(inv["账面价值"]) for inv in account_inventory)

        # 计算平均成本
        avg_cost = abs(total_cost / total_quantity) if total_quantity != 0 else 0

        # 查询现有持仓
        cursor.execute(
            """
            SELECT * FROM positions
            WHERE ledger_id = ? AND account_id = ? AND code = ?
        """,
            (transaction["ledger_id"], transaction["account_id"], transaction["code"]),
        )
        position = cursor.fetchone()

        if total_quantity > 0.0001:
            # 有持仓，更新或插入
            if position:
                cursor.execute(
                    """
                    UPDATE positions
                    SET quantity = ?, avg_cost = ?, current_price = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE ledger_id = ? AND account_id = ? AND code = ?
                """,
                    (
                        total_quantity,
                        avg_cost,
                        transaction["price"],
                        transaction["ledger_id"],
                        transaction["account_id"],
                        transaction["code"],
                    ),
                )
            else:
                _cat = transaction.get("category")
                _curr = transaction.get("currency", "CNY")
                cursor.execute(
                    "SELECT id FROM categories WHERE name = ? LIMIT 1", (_cat or "",)
                )
                _rc = cursor.fetchone()
                _cat_id = _rc[0] if _rc else None
                cursor.execute(
                    "SELECT id FROM currencies WHERE code = ? LIMIT 1",
                    (_curr or "CNY",),
                )
                _rc = cursor.fetchone()
                _curr_id = _rc[0] if _rc else None
                if _cat_id is not None and _curr_id is not None:
                    cursor.execute(
                        """
                        INSERT INTO positions (ledger_id, account_id, code, name, category_id, currency_id,
                                              quantity, avg_cost, current_price)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            transaction["ledger_id"],
                            transaction["account_id"],
                            transaction["code"],
                            transaction["name"],
                            _cat_id,
                            _curr_id,
                            total_quantity,
                            avg_cost,
                            transaction["price"],
                        ),
                    )
        elif total_quantity <= 0.0001 and total_quantity >= -0.0001:
            # 清空持仓（数量为0或接近0）
            if position:
                cursor.execute(
                    """
                    DELETE FROM positions
                    WHERE ledger_id = ? AND account_id = ? AND code = ?
                """,
                    (
                        transaction["ledger_id"],
                        transaction["account_id"],
                        transaction["code"],
                    ),
                )
        else:
            # 空头寸（数量为负）- 也需要记录
            if position:
                cursor.execute(
                    """
                    UPDATE positions
                    SET quantity = ?, avg_cost = ?, current_price = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE ledger_id = ? AND account_id = ? AND code = ?
                """,
                    (
                        total_quantity,
                        avg_cost,
                        transaction["price"],
                        transaction["ledger_id"],
                        transaction["account_id"],
                        transaction["code"],
                    ),
                )
            else:
                _cat = transaction.get("category")
                _curr = transaction.get("currency", "CNY")
                cursor.execute(
                    "SELECT id FROM categories WHERE name = ? LIMIT 1", (_cat or "",)
                )
                _rc = cursor.fetchone()
                _cat_id = _rc[0] if _rc else None
                cursor.execute(
                    "SELECT id FROM currencies WHERE code = ? LIMIT 1",
                    (_curr or "CNY",),
                )
                _rc = cursor.fetchone()
                _curr_id = _rc[0] if _rc else None
                if _cat_id is not None and _curr_id is not None:
                    cursor.execute(
                        """
                        INSERT INTO positions (ledger_id, account_id, code, name, category_id, currency_id,
                                              quantity, avg_cost, current_price)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            transaction["ledger_id"],
                            transaction["account_id"],
                            transaction["code"],
                            transaction["name"],
                            _cat_id,
                            _curr_id,
                            total_quantity,
                            avg_cost,
                            transaction["price"],
                        ),
                    )

    def rebuild_all_positions(self):
        """重建所有持仓（从库存管理器同步到数据库）

        删除/修改交易后必须全量重建库存（force_full=True），否则内存中的库存
        与数据库交易不一致，会导致持仓错误或浮动损益消失。
        """
        try:
            cursor = self.conn.cursor()

            # 必须全量重建库存，确保与当前数据库交易记录一致
            self._rebuild_all_inventory(force_full=True)

            # 获取所有账本和账户的映射关系
            accounts_df = self.get_accounts()
            if accounts_df.empty:
                # 如果没有账户，清空所有持仓
                cursor.execute("DELETE FROM positions")
                self.conn.commit()
                logging.info("已清空所有持仓（无账户）")
                return

            # 创建账户名称到账户ID和账本ID的映射
            account_map = {}
            for _, account_row in accounts_df.iterrows():
                account_name = account_row["name"]
                account_id = account_row["id"]
                ledger_id = account_row["ledger_id"]
                account_map[account_name] = {
                    "account_id": account_id,
                    "ledger_id": ledger_id,
                }

            # 获取所有账本
            ledgers_df = self.get_ledgers()

            # 存储需要保留的持仓（用于后续删除不存在的持仓）
            positions_to_keep = set()

            # 遍历每个账本
            for _, ledger_row in ledgers_df.iterrows():
                ledger_id = int(ledger_row["id"])
                inventory_manager = self._get_inventory_manager(ledger_id)

                # 获取该账本下所有代码的库存
                inventory_list = inventory_manager.get_inventory_list(ledger_id)

                # 按代码和账户分组
                position_dict = {}
                for inv in inventory_list:
                    code = inv["代码"]
                    account_name = inv["账户"]

                    if account_name not in account_map:
                        continue

                    account_info = account_map[account_name]
                    if account_info["ledger_id"] != ledger_id:
                        continue

                    key = (ledger_id, account_info["account_id"], code)
                    if key not in position_dict:
                        position_dict[key] = {
                            "code": code,
                            "name": inv.get("名称", ""),
                            "category": "",  # 需要从交易记录中获取
                            "currency": inv.get("币种", "CNY"),
                            "quantity": 0.0,
                            "total_cost": 0.0,
                            "account_id": account_info["account_id"],
                            "ledger_id": ledger_id,
                        }

                    # 累加数量和成本
                    quantity = float(inv["数量"])
                    cost = float(inv["账面价值"])
                    position_dict[key]["quantity"] += quantity
                    position_dict[key]["total_cost"] += cost

                # 同步持仓到数据库
                for key, pos_data in position_dict.items():
                    ledger_id, account_id, code = key
                    total_quantity = pos_data["quantity"]
                    total_cost = pos_data["total_cost"]

                    # 计算平均成本
                    avg_cost = (
                        abs(total_cost / total_quantity)
                        if abs(total_quantity) > 0.0001
                        else 0.0
                    )

                    # 获取最新交易记录以获取名称、类别ID、当前价格、币种ID
                    cursor.execute(
                        """
                        SELECT name, category_id, price, currency_id
                        FROM transactions
                        WHERE ledger_id = ? AND account_id = ? AND code = ?
                        ORDER BY date DESC, id DESC
                        LIMIT 1
                    """,
                        (ledger_id, account_id, code),
                    )
                    trans_row = cursor.fetchone()

                    if trans_row:
                        pos_data["name"] = trans_row[0] or pos_data["name"]
                        pos_data["category_id"] = trans_row[1]
                        current_price = trans_row[2] or 0.0
                        pos_data["currency_id"] = trans_row[3]
                    else:
                        current_price = avg_cost if avg_cost > 0 else 0.0
                        pos_data["category_id"] = None
                        pos_data["currency_id"] = None
                        # 从 inv 的币种代码解析 currency_id
                        _cur_code = pos_data.get("currency") or "CNY"
                        cursor.execute(
                            "SELECT id FROM currencies WHERE code = ? LIMIT 1",
                            (_cur_code,),
                        )
                        r = cursor.fetchone()
                        pos_data["currency_id"] = r[0] if r else None
                    if not pos_data.get("category_id") or not pos_data.get(
                        "currency_id"
                    ):
                        if not pos_data.get("category_id"):
                            cursor.execute(
                                "SELECT id FROM categories ORDER BY id LIMIT 1"
                            )
                            r = cursor.fetchone()
                            pos_data["category_id"] = r[0] if r else None
                        if not pos_data.get("currency_id"):
                            cursor.execute(
                                "SELECT id FROM currencies WHERE code = 'CNY' LIMIT 1"
                            )
                            r = cursor.fetchone()
                            pos_data["currency_id"] = r[0] if r else None

                    cursor.execute(
                        """
                        SELECT id FROM positions
                        WHERE ledger_id = ? AND account_id = ? AND code = ?
                    """,
                        (ledger_id, account_id, code),
                    )
                    existing_position = cursor.fetchone()

                    if (
                        abs(total_quantity) > 0.0001
                        and pos_data.get("category_id")
                        and pos_data.get("currency_id")
                    ):
                        positions_to_keep.add((ledger_id, account_id, code))
                        if existing_position:
                            cursor.execute(
                                """
                                UPDATE positions
                                SET quantity = ?, avg_cost = ?, current_price = ?,
                                    name = ?, category_id = ?, currency_id = ?, updated_at = CURRENT_TIMESTAMP
                                WHERE ledger_id = ? AND account_id = ? AND code = ?
                            """,
                                (
                                    total_quantity,
                                    avg_cost,
                                    current_price,
                                    pos_data["name"],
                                    pos_data["category_id"],
                                    pos_data["currency_id"],
                                    ledger_id,
                                    account_id,
                                    code,
                                ),
                            )
                        else:
                            cursor.execute(
                                """
                                INSERT INTO positions (ledger_id, account_id, code, name, category_id, currency_id,
                                                      quantity, avg_cost, current_price)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                                (
                                    ledger_id,
                                    account_id,
                                    code,
                                    pos_data["name"],
                                    pos_data["category_id"],
                                    pos_data["currency_id"],
                                    total_quantity,
                                    avg_cost,
                                    current_price,
                                ),
                            )
                    else:
                        # 清空持仓（数量为0或接近0）
                        if existing_position:
                            cursor.execute(
                                """
                                DELETE FROM positions
                                WHERE ledger_id = ? AND account_id = ? AND code = ?
                            """,
                                (ledger_id, account_id, code),
                            )

            # 删除不再存在的持仓（不在库存中的持仓）
            cursor.execute("""
                SELECT ledger_id, account_id, code FROM positions
            """)
            all_positions = cursor.fetchall()
            for pos_row in all_positions:
                ledger_id, account_id, code = pos_row
                if (ledger_id, account_id, code) not in positions_to_keep:
                    cursor.execute(
                        """
                        DELETE FROM positions
                        WHERE ledger_id = ? AND account_id = ? AND code = ?
                    """,
                        (ledger_id, account_id, code),
                    )

            self.conn.commit()
            logging.info("已重新同步所有持仓")
        except Exception as e:
            logging.error(f"重建持仓时发生错误: {e}")
            self.conn.rollback()
            raise

    def _get_position_cost_cny_map(
        self, ledger_id: Optional[int] = None, account_id: Optional[int] = None
    ) -> dict:
        """从库存动态计算各持仓的人民币成本（账面价值×成本汇率），补全历史汇率后会自动正确"""
        accounts_df = self.get_accounts()
        if accounts_df.empty:
            return {}
        account_map = {}
        for _, row in accounts_df.iterrows():
            account_map[row["name"]] = {
                "account_id": row["id"],
                "ledger_id": row["ledger_id"],
            }
        ledgers_df = self.get_ledgers()
        if ledger_id is not None:
            ledgers_df = ledgers_df[ledgers_df["id"] == ledger_id]
        cost_cny_map = {}
        for _, ledger_row in ledgers_df.iterrows():
            lid = ledger_row["id"]
            inv_mgr = self._get_inventory_manager(int(lid))
            inv_list = inv_mgr.get_inventory_list(int(lid))
            for inv in inv_list:
                account_name = inv["账户"]
                if (
                    account_id
                    and account_map.get(account_name, {}).get("account_id")
                    != account_id
                ):
                    continue
                if account_map.get(account_name, {}).get("ledger_id") != lid:
                    continue
                code = inv["代码"]
                cost = float(inv["账面价值"])
                rate = float(inv.get("成本汇率") or inv.get("汇率") or 1.0)
                key = (lid, account_name, code)
                cost_cny_map[key] = cost_cny_map.get(key, 0.0) + cost * rate
        return cost_cny_map

    def get_positions(
        self, ledger_id: Optional[int] = None, account_id: Optional[int] = None
    ) -> pd.DataFrame:
        """获取持仓信息

        Args:
            ledger_id: 账本ID（可选）
            account_id: 账户ID（可选）

        Returns:
            pd.DataFrame: 持仓信息数据框，包含成本、市值、收益率等计算字段
        """
        query = """
            SELECT
                p.id,
                p.ledger_id,
                p.account_id,
                p.code,
                p.name,
                cat.name as category,
                c.code as currency,
                p.quantity,
                p.avg_cost,
                p.current_price,
                p.quantity * p.avg_cost as cost,
                p.quantity * p.current_price as market_value,
                l.name as ledger_name,
                a.name as account_name,
                c.symbol as currency_symbol,
                c.exchange_rate
            FROM positions p
            LEFT JOIN ledgers l ON p.ledger_id = l.id
            LEFT JOIN accounts a ON p.account_id = a.id
            LEFT JOIN categories cat ON p.category_id = cat.id
            LEFT JOIN currencies c ON p.currency_id = c.id
            WHERE p.quantity > 0
        """
        params = []

        if ledger_id:
            query += " AND p.ledger_id = ?"
            params.append(ledger_id)

        if account_id:
            query += " AND p.account_id = ?"
            params.append(account_id)

        query += " ORDER BY market_value DESC"

        df = pd.read_sql_query(query, self.conn, params=params)

        # 计算人民币市值；cost_cny 从库存动态计算（使用历史汇率，补全汇率后会自动正确）
        if not df.empty:
            cost_cny_map = self._get_position_cost_cny_map(ledger_id, account_id)
            df["cost_cny"] = df.apply(
                lambda r: cost_cny_map.get(
                    (r["ledger_id"], r["account_name"], r["code"]),
                    r["cost"] * r["exchange_rate"],
                ),
                axis=1,
            )
            df["market_value_cny"] = df["market_value"] * df["exchange_rate"]
            # 计算收益率
            df["profit"] = df["market_value"] - df["cost"]
            df["profit_cny"] = df["market_value_cny"] - df["cost_cny"]
            df["profit_rate"] = (df["profit"] / df["cost"] * 100).fillna(0)
            df["profit_rate_cny"] = (df["profit_cny"] / df["cost_cny"] * 100).fillna(0)

        return df

    def get_portfolio_stats(
        self, ledger_id: Optional[int] = None, account_id: Optional[int] = None
    ) -> Dict:
        """获取投资组合统计信息（收益率、资产占比等）

        Args:
            ledger_id: 账本ID（可选）
            account_id: 账户ID（可选）

        Returns:
            Dict: 投资组合统计信息字典，包含：
                - total_cost: 总成本（原币种）
                - total_value: 总市值（原币种）
                - total_cost_cny: 总成本（人民币）
                - total_value_cny: 总市值（人民币）
                - total_profit: 总盈亏（原币种）
                - total_profit_cny: 总盈亏（人民币）
                - profit_rate: 收益率（%）
                - position_count: 持仓数量
        """
        positions = self.get_positions(ledger_id, account_id)

        if positions.empty:
            return {
                "total_cost": 0,
                "total_value": 0,
                "total_cost_cny": 0,
                "total_value_cny": 0,
                "total_profit": 0,
                "total_profit_cny": 0,
                "profit_rate": 0,
                "position_count": 0,
            }

        total_cost_cny = positions["cost_cny"].sum()
        total_value_cny = positions["market_value_cny"].sum()
        total_profit_cny = total_value_cny - total_cost_cny
        profit_rate = (
            (total_profit_cny / total_cost_cny * 100) if total_cost_cny > 0 else 0
        )

        return {
            "total_cost": positions["cost"].sum(),
            "total_value": positions["market_value"].sum(),
            "total_cost_cny": total_cost_cny,
            "total_value_cny": total_value_cny,
            "total_profit": positions["market_value"].sum() - positions["cost"].sum(),
            "total_profit_cny": total_profit_cny,
            "profit_rate": profit_rate,
            "position_count": len(positions),
        }

    def get_realized_pl(
        self, ledger_id: Optional[int] = None, account_id: Optional[int] = None
    ) -> Dict:
        """获取已实现损益汇总及明细（按账本、可选按账户筛选）

        Args:
            ledger_id: 账本ID（必填时由调用方保证）
            account_id: 账户ID（可选）

        Returns:
            Dict: 含 total_cny（报表币种已实现损益合计）、details（明细列表，可序列化为 JSON）
        """
        if ledger_id is None:
            return {"total_cny": 0.0, "details": []}

        inv = self._get_inventory_manager(ledger_id)
        if inv is None:
            return {"total_cny": 0.0, "details": []}

        details = inv.get_realized_pl_details_list(ledger_id=ledger_id)
        if account_id is not None:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT name FROM accounts WHERE ledger_id = ? AND id = ?",
                (ledger_id, account_id),
            )
            row = cursor.fetchone()
            if row:
                account_name = row[0]
                details = [d for d in details if d.get("账户") == account_name]
            else:
                details = []

        def _to_serializable(obj):
            if hasattr(obj, "__float__"):
                return float(obj)
            if isinstance(obj, (list, tuple)):
                return [_to_serializable(x) for x in obj]
            if isinstance(obj, dict):
                return {k: _to_serializable(v) for k, v in obj.items()}
            return obj

        total_cny = 0.0
        for d in details:
            pl_cny = d.get("报表币种损益")
            if pl_cny is not None:
                total_cny += float(pl_cny)
            else:
                total_cny += float(d.get("利润", 0) or 0)

        return {
            "total_cny": round(total_cny, 2),
            "details": _to_serializable(details),
        }

    def get_asset_allocation(
        self, ledger_id: Optional[int] = None, account_id: Optional[int] = None
    ) -> pd.DataFrame:
        """获取资产占比分析

        Args:
            ledger_id: 账本ID（可选）
            account_id: 账户ID（可选）

        Returns:
            pd.DataFrame: 资产占比数据框，包含各持仓的市值占比
        """
        positions = self.get_positions(ledger_id, account_id)

        if positions.empty:
            return pd.DataFrame()

        total_value_cny = positions["market_value_cny"].sum()

        if total_value_cny > 0:
            positions["allocation_percent"] = (
                positions["market_value_cny"] / total_value_cny * 100
            ).round(2)
        else:
            positions["allocation_percent"] = 0

        return positions.sort_values("allocation_percent", ascending=False)

    def update_position_price(self, position_id: int, new_price: float) -> bool:
        """更新持仓市价

        Args:
            position_id: 持仓ID
            new_price: 新价格

        Returns:
            bool: 是否成功
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                UPDATE positions
                SET current_price = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """,
                (new_price, position_id),
            )
            self.conn.commit()
            return True
        except Exception as e:
            logging.error(f"更新持仓价格失败: {e}")
            return False

    def get_exchange_rate(self, currency: str) -> float:
        """获取汇率

        Args:
            currency: 币种代码

        Returns:
            float: 汇率（相对于人民币）
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT exchange_rate FROM currencies WHERE code = ?", (currency,)
        )
        result = cursor.fetchone()
        return result[0] if result else 1.0

    def convert_to_cny(self, amount: float, currency: str) -> float:
        """转换为人民币（使用当前汇率）

        Args:
            amount: 金额
            currency: 币种代码

        Returns:
            float: 人民币金额
        """
        rate = self.get_exchange_rate(currency)
        return amount * rate

    def get_latest_rate_before_date(
        self, currency_code: str, target_date: str
    ) -> Optional[float]:
        """获取指定日期之前（含）最新的汇率，用于交易记录使用历史汇率

        Args:
            currency_code: 币种代码
            target_date: 目标日期 "YYYY-MM-DD"

        Returns:
            float: 汇率，若无历史数据则返回 None
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

    def convert_to_cny_at_date(self, amount: float, currency: str, date: str) -> float:
        """按指定日期的汇率转换为人民币，若无历史汇率则回退到当前汇率

        Args:
            amount: 金额
            currency: 币种代码
            date: 交易日期 "YYYY-MM-DD"

        Returns:
            float: 人民币金额
        """
        rate = self.get_latest_rate_before_date(currency, date)
        if rate is None:
            rate = self.get_exchange_rate(currency)
        return amount * rate

    def get_accounts(self) -> pd.DataFrame:
        """获取账户列表（辅助方法）

        Returns:
            pd.DataFrame: 账户数据框（含 currency 列为 code，便于展示）
        """
        query = """
            SELECT a.*, l.name as ledger_name, c.code as currency, c.name as currency_name, c.symbol as currency_symbol
            FROM accounts a
            LEFT JOIN ledgers l ON a.ledger_id = l.id
            LEFT JOIN currencies c ON a.currency_id = c.id
            ORDER BY a.ledger_id, a.id
        """
        return pd.read_sql_query(query, self.conn)

    def get_ledgers(self) -> pd.DataFrame:
        """获取账本列表（辅助方法）

        Returns:
            pd.DataFrame: 账本数据框
        """
        query = "SELECT * FROM ledgers ORDER BY id"
        return pd.read_sql_query(query, self.conn)

    def get_positions_as_of_date(
        self,
        as_of_date: str,
        ledger_id: Optional[int] = None,
        account_id: Optional[int] = None,
    ) -> List[Dict]:
        """
        计算截至某日的持仓快照（按交易回溯，用于历史快照）。
        使用该账本的成本法（FIFO/WAC）计算数量与成本。

        Args:
            as_of_date: 截止日期 "YYYY-MM-DD"
            ledger_id: 账本 ID，必填
            account_id: 账户 ID，可选

        Returns:
            持仓列表，每项含 ledger_id, account_id, code, name, category_id, currency_id, quantity, avg_cost
        """
        if ledger_id is None:
            return []
        cost_method = self.get_ledger_cost_method(ledger_id)
        query = """
            SELECT
                t.ledger_id as 账本ID,
                t.ledger_id,
                t.account_id,
                t.id as 编号,
                t.date as 日期,
                t.code as 代码,
                t.name as 名称,
                CASE
                    WHEN t.type IN ('买入', '开仓') THEN t.quantity
                    WHEN t.type IN ('卖出', '平仓') THEN -t.quantity
                END as 数量,
                CASE
                    WHEN t.type IN ('买入', '开仓') THEN -t.amount
                    WHEN t.type IN ('卖出', '平仓') THEN t.amount
                END as 金额,
                a.name as 账户,
                c.code as 币种,
                c.exchange_rate as 汇率
            FROM transactions t
            LEFT JOIN accounts a ON t.account_id = a.id
            LEFT JOIN currencies c ON t.currency_id = c.id
            WHERE t.type IN ('买入', '卖出', '开仓', '平仓')
              AND t.date <= ?
              AND t.ledger_id = ?
        """
        params = [as_of_date, ledger_id]
        if account_id is not None:
            query += " AND t.account_id = ?"
            params.append(account_id)
        query += " ORDER BY t.date, t.id"
        df = pd.read_sql_query(query, self.conn, params=params)
        if df.empty:
            return []
        if "汇率" not in df.columns or df["汇率"].isna().all():
            df["汇率"] = 1.0
        df["汇率"] = df["汇率"].fillna(1.0)

        temp_fifo = FIFOInventory(enable_exchange_rate=True)
        temp_wac = WACInventory(enable_exchange_rate=True)
        if cost_method == COST_METHOD_WAC:
            temp_wac.add_stock_from_df(df)
            inv_manager = temp_wac
        else:
            temp_fifo.add_stock_from_df(df)
            inv_manager = temp_fifo

        accounts_df = pd.read_sql_query(
            "SELECT id, name FROM accounts WHERE ledger_id = ?",
            self.conn,
            params=[ledger_id],
        )
        account_name_to_id = dict(zip(accounts_df["name"], accounts_df["id"]))

        inventory_list = inv_manager.get_inventory_list(ledger_id)
        position_dict = {}
        for inv in inventory_list:
            code = inv["代码"]
            account_name = inv["账户"]
            quantity = float(inv["数量"])
            book_value = float(inv["账面价值"])
            if account_name not in account_name_to_id:
                continue
            aid = account_name_to_id[account_name]
            if account_id is not None and aid != account_id:
                continue
            key = (aid, code)
            if key not in position_dict:
                position_dict[key] = {"quantity": 0.0, "total_cost": 0.0}
            position_dict[key]["quantity"] += quantity
            position_dict[key]["total_cost"] += book_value

        if not position_dict:
            return []

        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT account_id, code, name, category_id, currency_id
            FROM (
                SELECT account_id, code, name, category_id, currency_id,
                       ROW_NUMBER() OVER (PARTITION BY account_id, code ORDER BY date DESC, id DESC) as rn
                FROM transactions
                WHERE ledger_id = ? AND date <= ?
                  AND type IN ('买入', '卖出', '开仓', '平仓')
            ) t
            WHERE rn = 1
        """,
            (ledger_id, as_of_date),
        )
        meta_rows = cursor.fetchall()
        meta = {
            (r[0], r[1]): {"name": r[2], "category_id": r[3], "currency_id": r[4]}
            for r in meta_rows
        }

        result = []
        for (aid, code), data in position_dict.items():
            qty = data["quantity"]
            total_cost = data["total_cost"]
            if abs(qty) < 0.0001:
                continue
            avg_cost = abs(total_cost / qty) if qty else 0.0
            m = meta.get((aid, code))
            if not m or m["category_id"] is None or m["currency_id"] is None:
                continue
            result.append(
                {
                    "ledger_id": ledger_id,
                    "account_id": aid,
                    "code": code,
                    "name": m["name"] or code,
                    "category_id": m["category_id"],
                    "currency_id": m["currency_id"],
                    "quantity": qty,
                    "avg_cost": avg_cost,
                }
            )
        return result
