"""
加权平均成本法 (WAC - Weighted Average Cost) 库存管理框架

支持多账户、多币种的加权平均成本库存管理
"""

import pandas as pd
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class WACInventoryRecord:
    """加权平均成本库存记录数据类"""

    code: str
    name: str
    quantity: Decimal
    total_cost: Decimal  # 总成本
    avg_cost: Decimal  # 平均成本
    account: str
    ledger_id: int = 0  # 账本ID，用于多账本隔离
    currency: str = "CNY"
    exchange_rate: Decimal = Decimal("1.0")


@dataclass
class WACPLDetail:
    """加权平均成本损益详情数据类"""

    date: str
    transaction_id: str
    code: str
    name: str
    sold_quantity: Decimal
    avg_cost: Decimal  # 卖出时的平均成本
    sell_price: Decimal  # 卖出单价
    income: Decimal  # 收入
    cost: Decimal  # 成本
    profit: Decimal  # 利润
    currency: str
    account: str
    ledger_id: int = 0  # 账本ID，用于多账本筛选
    exchange_rate: Decimal = Decimal("1.0")


class WACInventory:
    """加权平均成本库存管理系统

    支持多账户、多币种的加权平均成本库存管理
    """

    def __init__(self, enable_exchange_rate: bool = False):
        """初始化加权平均成本库存管理系统

        Args:
            enable_exchange_rate: 是否启用汇率换算功能，默认为False
        """
        # 库存结构: {(ledger_id, code): {account: WACInventoryRecord}}
        self.inventory: Dict[Tuple[int, str], Dict[str, WACInventoryRecord]] = {}
        self.realized_pl_details: List[WACPLDetail] = []
        self.has_currency_column: bool = True
        self.enable_exchange_rate: bool = enable_exchange_rate

    def _make_key(self, ledger_id: int, code: str) -> Tuple[int, str]:
        """生成库存键"""
        return (ledger_id, code)

    def add_stock_from_df(self, df: pd.DataFrame) -> None:
        """从DataFrame批量添加库存记录

        Args:
            df: 包含交易记录的DataFrame，必须包含列：编号、日期、代码、名称、数量、金额、账户
                如果启用汇率换算，还需要包含：汇率列
        """
        logger.info(f"开始处理 {len(df)} 条交易记录 (加权平均成本法)")

        # 检测输入是否有币种列
        self.has_currency_column = "币种" in df.columns

        if self.enable_exchange_rate and "汇率" not in df.columns:
            raise ValueError("启用汇率换算时，必须提供'汇率'列")

        df = df.copy()
        if "账本ID" not in df.columns:
            df["账本ID"] = 0

        df = df.sort_values(["日期", "编号"])

        for _, row in df.iterrows():
            ledger_id = int(row.get("账本ID", 0))
            self._process_single_transaction(row, ledger_id)

        logger.info("所有交易记录处理完成 (加权平均成本法)")

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
        exchange_rate: Decimal,
    ) -> None:
        """处理买入交易 - 使用加权平均成本法"""
        key = self._make_key(ledger_id, code)

        if key not in self.inventory:
            self.inventory[key] = {}

        if account not in self.inventory[key]:
            avg_cost = (book_value / quantity).quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_UP
            )
            self.inventory[key][account] = WACInventoryRecord(
                code=code,
                name=name,
                quantity=quantity,
                total_cost=book_value,
                avg_cost=avg_cost,
                account=account,
                ledger_id=ledger_id,
                currency=currency,
                exchange_rate=exchange_rate,
            )
        else:
            record = self.inventory[key][account]
            new_quantity = record.quantity + quantity
            new_total_cost = record.total_cost + book_value
            new_avg_cost = (new_total_cost / new_quantity).quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_UP
            )

            record.quantity = new_quantity
            record.total_cost = new_total_cost
            record.avg_cost = new_avg_cost
            if self.enable_exchange_rate:
                old_weight = (record.quantity - quantity) / new_quantity
                new_weight = quantity / new_quantity
                record.exchange_rate = (
                    record.exchange_rate * old_weight + exchange_rate * new_weight
                ).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

        logger.debug(
            f"买入完成: 账本{ledger_id} {code}, 数量: {quantity}, 账户: {account}"
        )

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
        exchange_rate: Decimal,
    ) -> None:
        """处理卖出交易 - 使用加权平均成本法"""
        key = self._make_key(ledger_id, code)

        if key not in self.inventory or account not in self.inventory[key]:
            if key not in self.inventory:
                self.inventory[key] = {}

            sell_price = (book_value / quantity).quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_UP
            )
            self.inventory[key][account] = WACInventoryRecord(
                code=code,
                name=name,
                quantity=-quantity,
                total_cost=-book_value,
                avg_cost=sell_price,
                account=account,
                ledger_id=ledger_id,
                currency=currency,
                exchange_rate=exchange_rate,
            )
            logger.warning(
                f"创建空头寸: 账本{ledger_id} {code}, 数量: {-quantity}, 账户: {account}"
            )
            return

        record = self.inventory[key][account]

        sell_cost = (quantity * record.avg_cost).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        profit = (book_value - sell_cost).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        sell_price = (book_value / quantity).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )

        pl_detail = WACPLDetail(
            date=date,
            transaction_id=transaction_id,
            code=code,
            name=name,
            sold_quantity=quantity,
            avg_cost=record.avg_cost,
            sell_price=sell_price,
            income=book_value,
            cost=sell_cost,
            profit=profit,
            currency=currency,
            account=account,
            ledger_id=ledger_id,
            exchange_rate=exchange_rate,
        )
        self.realized_pl_details.append(pl_detail)

        # 更新持仓
        new_quantity = record.quantity - quantity
        new_total_cost = (new_quantity * record.avg_cost).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        if abs(new_quantity) < Decimal("0.0001"):
            # 清空持仓（键为 (ledger_id, code)，不是 code）
            del self.inventory[key][account]
            if not self.inventory[key]:
                del self.inventory[key]
        else:
            record.quantity = new_quantity
            record.total_cost = new_total_cost
            # 平均成本保持不变

        logger.debug(
            f"卖出完成: {code}, 数量: {quantity}, 账户: {account}, 利润: {profit}"
        )

    def get_inventory(self, code: Optional[str] = None) -> pd.DataFrame:
        """获取库存信息

        Args:
            code: 商品代码，如果为None则返回所有库存

        Returns:
            库存记录的DataFrame
        """
        records = []

        if code:
            for (lid, c), accounts in self.inventory.items():
                if c == code:
                    for account, record in accounts.items():
                        records.append(record)
        else:
            for code_key, accounts in self.inventory.items():
                for account, record in accounts.items():
                    records.append(record)

        if not records:
            return pd.DataFrame()

        dict_records = []
        for record in records:
            record_dict = {
                "代码": record.code,
                "名称": record.name,
                "数量": record.quantity,
                "账面价值": record.total_cost,
                "平均成本": record.avg_cost,
                "账户": record.account,
            }
            if self.has_currency_column:
                record_dict["币种"] = record.currency
            if self.enable_exchange_rate:
                record_dict["汇率"] = record.exchange_rate
            dict_records.append(record_dict)

        return pd.DataFrame(dict_records)

    def get_inventory_list(
        self, ledger_id: Optional[int] = None, code: Optional[str] = None
    ) -> List[dict]:
        """获取库存信息（轻量级版）

        Args:
            ledger_id: 账本ID，如果为None则返回所有账本
            code: 商品代码，如果为None则返回所有库存

        Returns:
            库存记录的字典列表
        """
        records = []

        for (lid, c), accounts in self.inventory.items():
            if ledger_id is not None and lid != ledger_id:
                continue
            if code is not None and c != code:
                continue
            for account, record in accounts.items():
                records.append(record)

        if not records:
            return []

        result = []
        for record in records:
            record_dict = {
                "代码": record.code,
                "名称": record.name,
                "数量": record.quantity,
                "账面价值": record.total_cost,
                "平均成本": record.avg_cost,
                "账户": record.account,
                "账本ID": record.ledger_id,
            }
            if self.has_currency_column:
                record_dict["币种"] = record.currency
            if self.enable_exchange_rate:
                record_dict["汇率"] = record.exchange_rate
            result.append(record_dict)

        return result

    def get_total_quantity(self, code: str, account: Optional[str] = None) -> Decimal:
        """获取指定代码的总数量（键为 (ledger_id, code)，需遍历匹配 code）"""
        total = Decimal("0")
        for (lid, c), accounts in self.inventory.items():
            if c != code:
                continue
            if account:
                if account in accounts:
                    return accounts[account].quantity
                return Decimal("0")
            total += sum(record.quantity for record in accounts.values())
        return total

    def get_total_cost(self, code: str, account: Optional[str] = None) -> Decimal:
        """获取指定代码的总成本（键为 (ledger_id, code)，需遍历匹配 code）"""
        total = Decimal("0")
        for (lid, c), accounts in self.inventory.items():
            if c != code:
                continue
            if account:
                if account in accounts:
                    return accounts[account].total_cost
                return Decimal("0")
            total += sum(record.total_cost for record in accounts.values())
        return total

    def get_realized_pl_details(self) -> pd.DataFrame:
        """获取已实现损益详情"""
        if not self.realized_pl_details:
            return pd.DataFrame()

        dict_records = []
        for pl in self.realized_pl_details:
            pl_dict = {
                "日期": pl.date,
                "编号": pl.transaction_id,
                "代码": pl.code,
                "名称": pl.name,
                "出账数量": pl.sold_quantity,
                "平均成本": pl.avg_cost,
                "卖出单价": pl.sell_price,
                "收入": pl.income,
                "成本": pl.cost,
                "利润": pl.profit,
                "账户": pl.account,
                "账本ID": pl.ledger_id,
            }
            if self.has_currency_column:
                pl_dict["币种"] = pl.currency
            if self.enable_exchange_rate:
                pl_dict["汇率"] = pl.exchange_rate
                pl_dict["报表币种损益"] = (pl.profit * pl.exchange_rate).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
            dict_records.append(pl_dict)

        return pd.DataFrame(dict_records)

    def get_realized_pl_details_list(
        self,
        code: Optional[str] = None,
        ledger_id: Optional[int] = None,
    ) -> List[dict]:
        """获取已实现损益详情（轻量级版）"""
        if not self.realized_pl_details:
            return []

        records = self.realized_pl_details
        if code:
            records = [pl for pl in records if pl.code == code]
        if ledger_id is not None:
            records = [pl for pl in records if pl.ledger_id == ledger_id]

        if not records:
            return []

        result = []
        for pl in records:
            pl_dict = {
                "日期": pl.date,
                "编号": pl.transaction_id,
                "代码": pl.code,
                "名称": pl.name,
                "出账数量": pl.sold_quantity,
                "平均成本": pl.avg_cost,
                "卖出单价": pl.sell_price,
                "收入": pl.income,
                "成本": pl.cost,
                "利润": pl.profit,
                "账户": pl.account,
                "账本ID": pl.ledger_id,
            }
            if self.has_currency_column:
                pl_dict["币种"] = pl.currency
            if self.enable_exchange_rate:
                pl_dict["汇率"] = pl.exchange_rate
                pl_dict["报表币种损益"] = (pl.profit * pl.exchange_rate).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
            result.append(pl_dict)

        return result

    def get_inventory_summary(self) -> pd.DataFrame:
        """获取库存汇总信息"""
        summary_data = []

        for code, accounts in self.inventory.items():
            for account, record in accounts.items():
                summary_data.append(
                    {
                        "代码": code,
                        "账户": account,
                        "总数量": record.quantity,
                        "总成本": record.total_cost,
                        "平均成本": record.avg_cost,
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
    print("加权平均成本法 (WAC) 示例")
    print("=" * 80)

    data = {
        "编号": [1, 2, 3, 4],
        "日期": ["2025/2/1", "2025/2/2", "2025/2/3", "2025/2/4"],
        "代码": ["HK.00881", "HK.00881", "HK.00881", "HK.00881"],
        "名称": ["中升控股", "中升控股", "中升控股", "中升控股"],
        "数量": [100, 100, -50, 50],
        "价格": [10, 12, 15, 8],
        "金额": [1000, 1200, -750, 400],
        "账户": ["富途证券-港币", "富途证券-港币", "富途证券-港币", "富途证券-港币"],
    }

    df = pd.DataFrame(data)

    inventory = WACInventory(enable_exchange_rate=False)
    inventory.add_stock_from_df(df)

    print("\n当前库存:")
    print(inventory.get_inventory())

    print("\n库存汇总:")
    print(inventory.get_inventory_summary())

    print("\n已实现损益:")
    print(inventory.get_realized_pl_details())

    print("\n" + "=" * 80)
    print("说明:")
    print("1. 加权平均成本法在每次买入时重新计算平均成本")
    print("2. 卖出时使用当前的平均成本计算成本")
    print("3. 适用于频繁交易、不需要追踪具体批次的场景")
    print("=" * 80)
