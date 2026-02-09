import pandas as pd
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Tuple, Optional, Union
from dataclasses import dataclass
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class InventoryRecord:
    """库存记录数据类"""

    batch_id: str
    date: str
    code: str
    name: str
    quantity: Decimal
    book_value: Decimal
    account: str
    ledger_id: int = 0  # 账本ID，用于多账本隔离
    currency: str = "CNY"
    exchange_rate: Decimal = Decimal("1.0")  # 汇率，默认为1.0


@dataclass
class PLDetail:
    """损益详情数据类"""

    date: str
    transaction_id: str
    inventory_id: str
    code: str
    name: str
    original_quantity: Decimal
    original_book_value: Decimal
    sold_quantity: Decimal
    remaining_quantity: Decimal
    remaining_book_value: Decimal
    income: Decimal
    cost: Decimal
    profit: Decimal
    currency: str
    account: str
    exchange_rate: Decimal = Decimal("1.0")  # 当前汇率（卖出/平仓时的汇率），默认为1.0
    cost_exchange_rate: Decimal = Decimal("1.0")  # 成本汇率（买入时的汇率），默认为1.0


class FIFOInventory:
    """FIFO库存管理系统

    支持多账本、多账户、多币种的先进先出库存管理
    """

    def __init__(self, enable_exchange_rate: bool = False):
        """初始化FIFO库存管理系统

        Args:
            enable_exchange_rate: 是否启用汇率换算功能，默认为False
        """
        self.inventory: Dict[Tuple[int, str], List[InventoryRecord]] = {}
        self.realized_pl_details: List[PLDetail] = []
        self.batch_counter = 1
        self.has_currency_column: bool = True
        self.enable_exchange_rate: bool = enable_exchange_rate

    def _make_key(self, ledger_id: int, code: str) -> Tuple[int, str]:
        """生成库存键"""
        return (ledger_id, code)

    def add_stock_from_df(self, df: pd.DataFrame) -> None:
        """从DataFrame批量添加库存记录

        Args:
            df: 包含交易记录的DataFrame，必须包含列：账本ID(可选)、代码、数量、日期、名称、金额、账户
                如果启用汇率换算，还需要包含：汇率列
                如果有账本ID列，则按账本隔离；否则默认账本ID为0
        """
        logger.info(f"开始处理 {len(df)} 条交易记录")

        self.has_currency_column = "币种" in df.columns

        if self.enable_exchange_rate and "汇率" not in df.columns:
            raise ValueError("启用汇率换算时，必须提供'汇率'列")

        df = df.copy()
        if "账本ID" not in df.columns:
            df["账本ID"] = 0

        grouped = df.groupby(["账本ID", "代码"])

        for (ledger_id, code), group_df in grouped:
            logger.debug(f"处理账本 {ledger_id} 代码 {code} 的 {len(group_df)} 条记录")

            key = self._make_key(int(ledger_id), str(code))
            if key not in self.inventory:
                self.inventory[key] = []

            group_df = group_df.sort_values("日期")

            for _, row in group_df.iterrows():
                self._process_single_transaction(row, int(ledger_id))

        logger.info("所有交易记录处理完成")

    def _process_single_transaction(self, row: pd.Series, ledger_id: int = 0) -> None:
        """处理单笔交易

        Args:
            row: 单笔交易记录
            ledger_id: 账本ID
        """
        try:
            code = str(row["代码"])
            quantity = Decimal(str(row["数量"]))
            date = str(row["日期"])
            name = str(row["名称"])
            book_value = Decimal(str(row["金额"]))
            account = str(row["账户"])
            currency = str(row.get("币种", "CNY"))
            transaction_id = str(row["编号"])

            if self.enable_exchange_rate:
                exchange_rate = Decimal(str(row["汇率"]))
            else:
                exchange_rate = Decimal("1.0")

        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"数据验证失败: {e}")
            raise ValueError(f"交易记录数据格式错误: {e}")

        # 检查该交易是否已经处理过（通过 batch_id 避免重复）
        key = self._make_key(ledger_id, code)
        if key in self.inventory:
            for record in self.inventory[key]:
                if record.batch_id == transaction_id and record.account == account:
                    logger.debug(
                        f"交易 {transaction_id} 已处理过，跳过: {code} {account}"
                    )
                    return

        if quantity > Decimal("0"):
            self._handle_buy_transaction(
                ledger_id,
                code,
                quantity,
                abs(book_value),
                date,
                name,
                account,
                currency,
                transaction_id,
                exchange_rate,
            )
        elif quantity < Decimal("0"):
            self._handle_sell_transaction(
                ledger_id,
                code,
                -quantity,
                abs(book_value),
                date,
                name,
                account,
                currency,
                transaction_id,
                exchange_rate,
            )
        else:
            logger.warning(f"数量为0的交易被忽略: {transaction_id}")

    def _handle_buy_transaction(
        self,
        ledger_id: int,
        code: str,
        quantity: Decimal,
        book_value: Decimal,
        date: str,
        name: str,
        account: str,
        currency: str,
        transaction_id: str,
        exchange_rate: Decimal = Decimal("1.0"),
    ) -> None:
        """处理买入交易"""
        key = self._make_key(ledger_id, code)

        if key not in self.inventory:
            self.inventory[key] = []

        pl_details, remaining_quantity = self.cover_short_position(
            ledger_id,
            code,
            quantity,
            book_value,
            date,
            name,
            account,
            currency,
            transaction_id,
            exchange_rate,
        )
        self.realized_pl_details.extend(pl_details)

        if remaining_quantity > Decimal("0"):
            total_quantity = quantity
            allocated_book_value = (
                remaining_quantity / total_quantity * book_value
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            record = InventoryRecord(
                batch_id=transaction_id,
                date=date,
                code=code,
                name=name,
                quantity=remaining_quantity,
                book_value=allocated_book_value,
                account=account,
                ledger_id=ledger_id,
                currency=currency,
                exchange_rate=exchange_rate,
            )

            self.inventory[key].append(record)
            self.inventory[key].sort(key=lambda x: x.date)

    def _handle_sell_transaction(
        self,
        ledger_id: int,
        code: str,
        quantity: Decimal,
        book_value: Decimal,
        date: str,
        name: str,
        account: str,
        currency: str,
        transaction_id: str,
        exchange_rate: Decimal = Decimal("1.0"),
    ) -> None:
        """处理卖出交易"""
        key = self._make_key(ledger_id, code)

        if key not in self.inventory:
            self.inventory[key] = []

        pl_details = self.remove_stock(
            ledger_id,
            code,
            quantity,
            book_value,
            date,
            name,
            account,
            currency,
            transaction_id,
            exchange_rate,
        )
        self.realized_pl_details.extend(pl_details)

    def remove_stock(
        self,
        ledger_id: int,
        code: str,
        quantity: Decimal,
        sell_book_value: Optional[Decimal] = None,
        sell_date: Optional[str] = None,
        name: Optional[str] = None,
        account: Optional[str] = None,
        currency: Optional[str] = None,
        sell_id: Optional[str] = None,
        exchange_rate: Decimal = Decimal("1.0"),
    ) -> List[PLDetail]:
        """从库存中移除指定数量的商品，支持空头寸（库存不足时创建负库存）

        Args:
            ledger_id: 账本ID
            code: 商品代码
            quantity: 移除数量
            sell_book_value: 销售账面价值（可选，用于计算损益）
            sell_date: 销售日期
            name: 商品名称
            account: 账户
            currency: 币种
            sell_id: 卖出交易编号

        Returns:
            已实现损益详情列表
        """
        key = self._make_key(ledger_id, code)

        if quantity <= Decimal("0"):
            raise ValueError("移除数量必须大于0")

        if key not in self.inventory:
            self.inventory[key] = []

        logger.debug(
            f"开始移除库存: 账本{ledger_id} {code}, 数量: {quantity}, 账户: {account}"
        )

        original_quantity = quantity
        removed_records = []
        pl_details = []

        account_batches = self._get_account_batches(ledger_id, code, account, currency)

        remaining_quantity = self._process_inventory_removal(
            key, account_batches, quantity, removed_records
        )

        if remaining_quantity > Decimal("0"):
            self._create_short_position(
                ledger_id,
                code,
                remaining_quantity,
                sell_book_value,
                sell_date,
                name,
                account,
                currency,
                sell_id,
                original_quantity,
                removed_records,
                exchange_rate,
            )

        if sell_book_value is not None and removed_records:
            pl_details = self._calculate_realized_pl(
                removed_records,
                sell_book_value,
                sell_date,
                sell_id,
                code,
                name,
                account,
                currency,
                original_quantity,
                exchange_rate,
            )

        logger.debug(f"库存移除完成，生成 {len(pl_details)} 条损益记录")
        return pl_details

    def _get_account_batches(
        self, ledger_id: int, code: str, account: str, currency: Optional[str] = None
    ) -> List[InventoryRecord]:
        """获取指定账户的正数库存批次"""
        key = self._make_key(ledger_id, code)
        batches = self.inventory.get(key, [])
        return [
            batch
            for batch in batches
            if batch.account == account
            and batch.quantity > 0
            and (currency is None or batch.currency == currency)
        ]

    def _process_inventory_removal(
        self,
        key: Tuple[int, str],
        account_batches: List[InventoryRecord],
        quantity: Decimal,
        removed_records: List[dict],
    ) -> Decimal:
        """处理库存移除，返回剩余未处理数量"""
        remaining_quantity = quantity

        for batch in account_batches[:]:
            if remaining_quantity <= Decimal("0"):
                break

            if batch.quantity <= remaining_quantity:
                removed_records.append(
                    {
                        "编号": batch.batch_id,
                        "数量": batch.quantity,
                        "账面价值": batch.book_value,
                        "成本汇率": batch.exchange_rate,
                    }
                )
                remaining_quantity -= batch.quantity
                self.inventory[key].remove(batch)
            else:
                allocated_book_value = (
                    remaining_quantity / batch.quantity * batch.book_value
                ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

                removed_records.append(
                    {
                        "编号": batch.batch_id,
                        "数量": remaining_quantity,
                        "账面价值": allocated_book_value,
                        "成本汇率": batch.exchange_rate,
                    }
                )

                batch.quantity -= remaining_quantity
                batch.book_value -= allocated_book_value
                remaining_quantity = Decimal("0")

        return remaining_quantity

    def _create_short_position(
        self,
        ledger_id: int,
        code: str,
        quantity: Decimal,
        sell_book_value: Decimal,
        sell_date: str,
        name: str,
        account: str,
        currency: str,
        sell_id: str,
        original_quantity: Decimal,
        removed_records: List[dict],
        exchange_rate: Decimal = Decimal("1.0"),
    ) -> None:
        """创建空头寸"""
        key = self._make_key(ledger_id, code)

        allocated_short_book_value = (
            quantity / original_quantity * sell_book_value
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        short_position = InventoryRecord(
            batch_id=sell_id,
            date=sell_date,
            code=code,
            name=name,
            quantity=-quantity,
            book_value=-allocated_short_book_value,
            account=account,
            ledger_id=ledger_id,
            currency=currency,
            exchange_rate=exchange_rate,
        )

        if key not in self.inventory:
            self.inventory[key] = []
        self.inventory[key].append(short_position)
        removed_records.append(
            {
                "编号": sell_id,
                "数量": -quantity,
                "账面价值": -allocated_short_book_value,
                "成本汇率": exchange_rate,
            }
        )

    def _calculate_realized_pl(
        self,
        removed_records: List[dict],
        sell_book_value: Decimal,
        sell_date: str,
        sell_id: str,
        code: str,
        name: str,
        account: str,
        currency: str,
        original_quantity: Decimal,
        exchange_rate: Decimal = Decimal("1.0"),
    ) -> List[PLDetail]:
        """计算已实现损益详情"""
        normal_records = [r for r in removed_records if r["数量"] > 0]

        if not normal_records:
            return []

        total_sell_quantity = sum(r["数量"] for r in normal_records)
        normal_ratio = total_sell_quantity / original_quantity
        total_sell_book_value = (sell_book_value * normal_ratio).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        pl_details = []
        allocated_income = Decimal("0")

        for i, record in enumerate(normal_records):
            original_quantity, original_book_value = self._get_original_batch_info(
                code, record["编号"], record["数量"], record["账面价值"]
            )

            cost_exchange_rate = record.get("成本汇率", Decimal("1.0"))

            cost_per_unit = (original_book_value / original_quantity).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            cost = (record["数量"] * cost_per_unit).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )

            # 按比例分配收入，确保总和精确等于total_sell_book_value
            if i == len(normal_records) - 1:
                # 最后一条记录：使用总金额减去已分配金额，确保总和精确等于total_sell_book_value
                batch_income = total_sell_book_value - allocated_income
                # 四舍五入到2位小数（由于前面已经四舍五入，这里通常不需要再次四舍五入，但为了保持一致性还是进行四舍五入）
                batch_income = batch_income.quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
            else:
                # 前面记录：按比例计算并四舍五入
                batch_income = (
                    (record["数量"] / total_sell_quantity) * total_sell_book_value
                ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                allocated_income += batch_income

            pl_detail = PLDetail(
                date=sell_date,
                transaction_id=sell_id,
                inventory_id=record["编号"],
                code=code,
                name=name,
                original_quantity=original_quantity,
                original_book_value=abs(original_book_value),
                sold_quantity=record["数量"],
                remaining_quantity=original_quantity - record["数量"],
                remaining_book_value=abs(original_book_value - record["账面价值"]),
                income=batch_income,
                cost=abs(record["账面价值"]),
                profit=(batch_income - abs(record["账面价值"])).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                ),
                currency=currency,
                account=account,
                exchange_rate=exchange_rate,  # 当前汇率（卖出时的汇率）
                cost_exchange_rate=cost_exchange_rate,  # 成本汇率（买入时的汇率）
            )
            pl_details.append(pl_detail)

        return pl_details

    def _get_original_batch_info(
        self, code: str, batch_id: str, sold_quantity: Decimal, sold_book_value: Decimal
    ) -> Tuple[Decimal, Decimal]:
        """获取批次的原始数量和账面价值"""
        for batches in self.inventory.values():
            for batch in batches:
                if batch.batch_id == batch_id:
                    original_quantity = batch.quantity + sold_quantity
                    original_book_value = batch.book_value + sold_book_value
                    return original_quantity, original_book_value
        return sold_quantity, sold_book_value

    def cover_short_position(
        self,
        ledger_id: int,
        code: str,
        quantity: Decimal,
        buy_book_value: Decimal,
        buy_date: str,
        name: str,
        account: str,
        currency: str,
        buy_id: str,
        exchange_rate: Decimal = Decimal("1.0"),
    ) -> Tuple[List[PLDetail], Decimal]:
        """平仓空头寸

        Args:
            ledger_id: 账本ID
            code: 商品代码
            quantity: 买入数量
            buy_book_value: 买入账面价值
            buy_date: 买入日期
            name: 商品名称
            account: 账户
            currency: 币种
            buy_id: 买入交易编号

        Returns:
            tuple: (已实现损益详情列表, 剩余数量)
        """
        key = self._make_key(ledger_id, code)

        if key not in self.inventory:
            return [], quantity

        logger.debug(
            f"开始平仓空头寸: 账本{ledger_id} {code}, 数量: {quantity}, 账户: {account}"
        )

        pl_details = []
        remaining_quantity = quantity

        short_positions = self._get_short_positions(ledger_id, code, account)

        for short_pos in short_positions[:]:
            if remaining_quantity <= Decimal("0"):
                break

            cover_result = self._process_short_position_cover(
                ledger_id,
                code,
                short_pos,
                remaining_quantity,
                buy_book_value,
                quantity,
                buy_date,
                buy_id,
                name,
                account,
                currency,
                exchange_rate,
            )

            if cover_result:
                pl_details.append(cover_result)
                remaining_quantity = cover_result.remaining_quantity

        logger.debug(f"空头寸平仓完成，剩余数量: {remaining_quantity}")
        return pl_details, remaining_quantity

    def _get_short_positions(
        self, ledger_id: int, code: str, account: str
    ) -> List[InventoryRecord]:
        """获取指定账户的空头寸，按日期排序（FIFO）"""
        key = self._make_key(ledger_id, code)
        batches = self.inventory.get(key, [])
        short_positions = [
            batch
            for batch in batches
            if batch.account == account and batch.quantity < 0
        ]
        short_positions.sort(key=lambda x: x.date)
        return short_positions

    def _process_short_position_cover(
        self,
        ledger_id: int,
        code: str,
        short_pos: InventoryRecord,
        remaining_quantity: Decimal,
        buy_book_value: Decimal,
        total_buy_quantity: Decimal,
        buy_date: str,
        buy_id: str,
        name: str,
        account: str,
        currency: str,
        exchange_rate: Decimal = Decimal("1.0"),
    ) -> Optional[PLDetail]:
        """处理单个空头寸的平仓"""
        short_quantity = abs(short_pos.quantity)
        short_book_value = short_pos.book_value

        if short_quantity <= remaining_quantity:
            return self._cover_full_short_position(
                ledger_id,
                code,
                short_pos,
                short_quantity,
                buy_book_value,
                total_buy_quantity,
                buy_date,
                buy_id,
                name,
                account,
                currency,
                exchange_rate,
            )
        else:
            return self._cover_partial_short_position(
                ledger_id,
                code,
                short_pos,
                remaining_quantity,
                buy_book_value,
                total_buy_quantity,
                buy_date,
                buy_id,
                name,
                account,
                currency,
                exchange_rate,
            )

    def _cover_full_short_position(
        self,
        ledger_id: int,
        code: str,
        short_pos: InventoryRecord,
        cover_quantity: Decimal,
        buy_book_value: Decimal,
        total_buy_quantity: Decimal,
        buy_date: str,
        buy_id: str,
        name: str,
        account: str,
        currency: str,
        exchange_rate: Decimal = Decimal("1.0"),
    ) -> PLDetail:
        """完全平仓空头寸"""
        key = self._make_key(ledger_id, code)

        short_income = abs(short_pos.book_value)

        cover_cost_per_unit = (buy_book_value / total_buy_quantity).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        cover_cost = (cover_quantity * cover_cost_per_unit).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        profit = (short_income - cover_cost).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        pl_detail = PLDetail(
            date=buy_date,
            transaction_id=buy_id,
            inventory_id=short_pos.batch_id,
            code=code,
            name=name,
            original_quantity=short_pos.quantity,
            original_book_value=abs(short_pos.book_value),
            sold_quantity=-cover_quantity,
            remaining_quantity=Decimal("0"),
            remaining_book_value=Decimal("0"),
            income=abs(short_income),
            cost=cover_cost,
            profit=profit,
            currency=currency,
            account=account,
            exchange_rate=exchange_rate,
            cost_exchange_rate=short_pos.exchange_rate,
        )

        self.inventory[key].remove(short_pos)

        return pl_detail

    def _cover_partial_short_position(
        self,
        ledger_id: int,
        code: str,
        short_pos: InventoryRecord,
        cover_quantity: Decimal,
        buy_book_value: Decimal,
        total_buy_quantity: Decimal,
        buy_date: str,
        buy_id: str,
        name: str,
        account: str,
        currency: str,
        exchange_rate: Decimal = Decimal("1.0"),
    ) -> PLDetail:
        """部分平仓空头寸"""
        key = self._make_key(ledger_id, code)

        short_quantity = abs(short_pos.quantity)
        short_book_value = abs(short_pos.book_value)

        short_income = (short_book_value * cover_quantity / short_quantity).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        cover_cost_per_unit = (buy_book_value / total_buy_quantity).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        cover_cost = (cover_quantity * cover_cost_per_unit).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        profit = (short_income - cover_cost).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        remaining_short_quantity = short_quantity - cover_quantity
        remaining_short_book_value = (short_book_value - short_income).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        short_pos.quantity = -remaining_short_quantity
        short_pos.book_value = -remaining_short_book_value

        pl_detail = PLDetail(
            date=buy_date,
            transaction_id=buy_id,
            inventory_id=short_pos.batch_id,
            code=code,
            name=name,
            original_quantity=-short_quantity,
            original_book_value=short_book_value,
            sold_quantity=-cover_quantity,
            remaining_quantity=-remaining_short_quantity,
            remaining_book_value=remaining_short_book_value.quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            ),
            income=abs(short_income),
            cost=cover_cost,
            profit=profit,
            currency=currency,
            account=account,
            exchange_rate=exchange_rate,
            cost_exchange_rate=short_pos.exchange_rate,
        )

        return pl_detail

    def get_inventory(
        self, ledger_id: Optional[int] = None, code: Optional[str] = None
    ) -> pd.DataFrame:
        """获取库存信息

        Args:
            ledger_id: 账本ID，如果为None则返回所有账本
            code: 商品代码，如果为None则返回所有代码

        Returns:
            库存记录的DataFrame
        """
        records = []
        for (lid, c), batches in self.inventory.items():
            if ledger_id is not None and lid != ledger_id:
                continue
            if code is not None and c != code:
                continue
            records.extend(batches)

        if not records:
            return pd.DataFrame()

        dict_records = []
        for record in records:
            record_dict = {
                "库存编号": record.batch_id,
                "库存日期": record.date,
                "代码": record.code,
                "名称": record.name,
                "数量": record.quantity,
                "账面价值": record.book_value,
                "账户": record.account,
                "账本ID": record.ledger_id,
            }
            if self.has_currency_column:
                record_dict["币种"] = record.currency
            if self.enable_exchange_rate:
                record_dict["成本汇率"] = record.exchange_rate
            dict_records.append(record_dict)

        return pd.DataFrame(dict_records)

    def get_inventory_list(
        self, ledger_id: Optional[int] = None, code: Optional[str] = None
    ) -> List[dict]:
        """获取库存信息（轻量级版）"""
        records = []
        for (lid, c), batches in self.inventory.items():
            if ledger_id is not None and lid != ledger_id:
                continue
            if code is not None and c != code:
                continue
            records.extend(batches)

        if not records:
            return []

        result = []
        for record in records:
            record_dict = {
                "库存编号": record.batch_id,
                "库存日期": record.date,
                "代码": record.code,
                "名称": record.name,
                "数量": record.quantity,
                "账面价值": record.book_value,
                "账户": record.account,
                "账本ID": record.ledger_id,
            }
            if self.has_currency_column:
                record_dict["币种"] = record.currency
            if self.enable_exchange_rate:
                record_dict["成本汇率"] = record.exchange_rate
            result.append(record_dict)
        return result

    def get_total_quantity(
        self, ledger_id: int, code: str, account: Optional[str] = None
    ) -> Decimal:
        """获取指定代码的总数量"""
        key = self._make_key(ledger_id, code)
        batches = self.inventory.get(key, [])
        if account:
            batches = [b for b in batches if b.account == account]
        return sum(b.quantity for b in batches)

    def get_total_cost(
        self, ledger_id: int, code: str, account: Optional[str] = None
    ) -> Decimal:
        """获取指定代码的总成本"""
        key = self._make_key(ledger_id, code)
        batches = self.inventory.get(key, [])
        if account:
            batches = [b for b in batches if b.account == account]
        return sum(b.book_value for b in batches)

    def get_inventory_list(
        self, ledger_id: Optional[int] = None, code: Optional[str] = None
    ) -> List[dict]:
        """获取库存信息（轻量级版）"""
        records = []
        for (lid, c), batches in self.inventory.items():
            if ledger_id is not None and lid != ledger_id:
                continue
            if code is not None and c != code:
                continue
            records.extend(batches)

        if not records:
            return []

        result = []
        for record in records:
            record_dict = {
                "库存编号": record.batch_id,
                "库存日期": record.date,
                "代码": record.code,
                "名称": record.name,
                "数量": record.quantity,
                "账面价值": record.book_value,
                "账户": record.account,
                "账本ID": record.ledger_id,
            }
            if self.has_currency_column:
                record_dict["币种"] = record.currency
            if self.enable_exchange_rate:
                record_dict["成本汇率"] = record.exchange_rate
            result.append(record_dict)
        return result

    def get_realized_pl_details(self) -> pd.DataFrame:
        """获取已实现损益详情

        Returns:
            已实现损益详情的DataFrame
        """
        if not self.realized_pl_details:
            return pd.DataFrame()

        # 转换为字典格式以保持兼容性
        dict_records = []
        for pl in self.realized_pl_details:
            pl_dict = {
                "日期": pl.date,
                "编号": pl.transaction_id,
                "库存编号": pl.inventory_id,
                "代码": pl.code,
                "名称": pl.name,
                "数量": pl.original_quantity,
                "账面价值": pl.original_book_value,
                "出账数量": pl.sold_quantity,
                "剩余数量": pl.remaining_quantity,
                "剩余账面价值": pl.remaining_book_value,
                "收入": pl.income,
                "成本": pl.cost,
                "利润": pl.profit,
                "账户": pl.account,
            }
            if self.has_currency_column:
                pl_dict["币种"] = pl.currency
            if self.enable_exchange_rate:
                pl_dict["当前汇率"] = pl.exchange_rate
                pl_dict["成本汇率"] = pl.cost_exchange_rate
                # 计算报表币种损益：收入*当前汇率 - 成本*成本汇率
                pl_dict["报表币种损益"] = (
                    pl.income * pl.exchange_rate - pl.cost * pl.cost_exchange_rate
                ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            dict_records.append(pl_dict)

        return pd.DataFrame(dict_records)

    def get_realized_pl_details_list(self, code: Optional[str] = None) -> List[dict]:
        """
        获取已实现损益详情（轻量级版），直接返回 List[dict]，不转换为 DataFrame。

        Args:
            code: 商品代码，如果指定则只返回该代码的损益记录

        Returns:
            已实现损益记录的字典列表
        """
        if not self.realized_pl_details:
            return []

        # 1. 确定要处理的数据源 (如果有code则先过滤，提升后续构建字典的效率)
        if code:
            # 假设 pl 对象中有 .code 属性
            records = [pl for pl in self.realized_pl_details if pl.code == code]
        else:
            records = self.realized_pl_details

        if not records:
            return []

        # 2. 直接构建字典列表 (使用列表推导式提升速度)
        result = []
        for pl in records:
            pl_dict = {
                "日期": pl.date,
                "编号": pl.transaction_id,
                "库存编号": pl.inventory_id,
                "代码": pl.code,
                "名称": pl.name,
                "数量": pl.original_quantity,
                "账面价值": pl.original_book_value,
                "出账数量": pl.sold_quantity,
                "剩余数量": pl.remaining_quantity,
                "剩余账面价值": pl.remaining_book_value,
                "收入": pl.income,
                "成本": pl.cost,
                "利润": pl.profit,
                "账户": pl.account,
            }
            if self.has_currency_column:
                pl_dict["币种"] = pl.currency
            if self.enable_exchange_rate:
                pl_dict["当前汇率"] = pl.exchange_rate
                pl_dict["成本汇率"] = pl.cost_exchange_rate
                # 计算报表币种损益：收入*当前汇率 - 成本*成本汇率
                pl_dict["报表币种损益"] = (
                    pl.income * pl.exchange_rate - pl.cost * pl.cost_exchange_rate
                ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            result.append(pl_dict)
        return result

    def get_inventory_summary(self) -> pd.DataFrame:
        """获取库存汇总信息

        Returns:
            按代码和账户汇总的库存信息
        """
        summary_data = []

        for code, records in self.inventory.items():
            # 按账户分组
            account_groups = {}
            for record in records:
                account = record.account
                if account not in account_groups:
                    account_groups[account] = []
                account_groups[account].append(record)

            for account, account_records in account_groups.items():
                total_quantity = sum(r.quantity for r in account_records)
                total_cost = sum(r.book_value for r in account_records)

                summary_data.append(
                    {
                        "代码": code,
                        "账户": account,
                        "总数量": total_quantity,
                        "总成本": total_cost,
                        "平均成本": (total_cost / total_quantity).quantize(
                            Decimal("0.01"), rounding=ROUND_HALF_UP
                        )
                        if total_quantity != 0
                        else Decimal("0"),
                        "批次数量": len(account_records),
                    }
                )

        return pd.DataFrame(summary_data)

    def clear_inventory(self) -> None:
        """清空所有库存和损益记录"""
        self.inventory.clear()
        self.realized_pl_details.clear()
        logger.info("库存和损益记录已清空")


# 使用示例
if __name__ == "__main__":
    print("=" * 80)
    print("示例1: 不启用汇率换算（默认）")
    print("=" * 80)

    data = {
        "编号": [1, 2, 3],
        "日期": ["2025/2/1", "2025/2/2", "2025/2/3"],
        "代码": ["HK.00881", "HK.00881", "HK.00881"],
        "名称": ["中升控股", "中升控股", "中升控股"],
        "数量": [1, 1, -3],
        "价格": [1, 2, 3],
        "金额": [1, 2, -9],
        "账户": ["富途证券-港币", "华泰证券-人民币", "华泰证券-人民币"],
    }

    df = pd.DataFrame(data)

    # 不启用汇率换算（默认）
    inventory = FIFOInventory(enable_exchange_rate=False)
    inventory.add_stock_from_df(df)

    print("\n全部库存（包含空头寸）:")
    inventory_df = inventory.get_inventory()
    print(inventory_df)

    print("\n库存汇总:")
    summary_df = inventory.get_inventory_summary()
    print(summary_df)

    print("\n已实现损益详情:")
    realized_pl = inventory.get_realized_pl_details_list()
    print(realized_pl)

    print("\n" + "=" * 80)
    print("示例2: 启用汇率换算")
    print("=" * 80)

    # 包含汇率列的数据
    data_with_rate = {
        "编号": [1, 2, 3, 4],
        "日期": ["2025/2/1", "2025/2/2", "2025/2/3", "2025/2/4"],
        "代码": ["HK.00881", "HK.00881", "HK.00881", "HK.00881"],
        "名称": ["中升控股", "中升控股", "中升控股", "中升控股"],
        "数量": [10, 10, -30, 10],
        "价格": [12, 13, 20, 30],
        "金额": [120, 130, -590, 300],
        "币种": ["HKD", "HKD", "HKD", "HKD"],
        "汇率": [0.91, 0.92, 0.93, 0.94],  # 港币对人民币汇率
        "账户": ["富途证券-港币", "富途证券-港币", "富途证券-港币", "富途证券-港币"],
    }

    df_with_rate = pd.DataFrame(data_with_rate)

    # 启用汇率换算
    inventory_with_rate = FIFOInventory(enable_exchange_rate=True)
    inventory_with_rate.add_stock_from_df(df_with_rate)

    print("\n全部库存（包含汇率）:")
    inventory_df_with_rate = inventory_with_rate.get_inventory()
    print(inventory_df_with_rate)

    print("\n库存汇总:")
    summary_df_with_rate = inventory_with_rate.get_inventory_summary()
    print(summary_df_with_rate)

    print("\n已实现损益详情（包含汇率）:")
    realized_pl_with_rate = inventory_with_rate.get_realized_pl_details()
    realized_pl_with_rate.to_csv("realized_pl_with_rate.csv", index=False)
    print(realized_pl_with_rate)

    print("\n" + "=" * 80)
    print("说明:")
    print("1. 默认不启用汇率换算: inventory = FIFOInventory()")
    print("2. 启用汇率换算: inventory = FIFOInventory(enable_exchange_rate=True)")
    print("3. 启用汇率换算时，数据必须包含'汇率'列")
    print("4. 已实现损益详情包含:")
    print("   - 当前汇率: 卖出/平仓时的汇率")
    print("   - 成本汇率: 买入时的汇率")
    print("   - 报表币种损益: 收入*当前汇率 - 成本*成本汇率")
    print("=" * 80)
