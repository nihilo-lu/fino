"""
收益率统计模块（SQLite 适配版）

参考 process_return_rate.py 的净值法逻辑，适配 investment_tracker 的 SQLite 数据库结构。

功能：
1. 从资金明细中获取本金投入/撤出作为发生金额
2. 根据净值确认份额（第一天净值为1）
3. 计算每日收益率
4. 写入收益率表
5. 处理4位小数精度的尾差，记录到尾差损益表
6. 支持按账本分别计算收益率，或处理所有活跃账本

净值法核心逻辑：
- 第一天：净值=1，份额=发生金额/净值
- 后续日期：单位净值=(当日净资产-发生金额)/前一日的总份额
- 有资金变动时：确认份额=发生金额/当日净值
- 总份额累计计算
- 当日收益率=(今日净值-昨日净值)/昨日净值
- 每日发生金额在当日末结算，影响当日净值计算结果

数据来源（SQLite）：
- 发生金额：fund_transactions (type=本金投入/本金撤出) + fund_transaction_entries
- 账户余额：account_balance_history
- 持仓市值：position_history
- 汇兑损益：暂不支持，默认0
"""

import pandas as pd
import logging
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional, Tuple
from decimal import Decimal, ROUND_HALF_UP
from utils.config_loader import get_config

try:
    config = get_config()
    SHARE_DECIMAL_PLACES = config.SHARE_DECIMAL_PLACES
    NAV_DECIMAL_PLACES = config.NAV_DECIMAL_PLACES
    RATE_DECIMAL_PLACES = config.RATE_DECIMAL_PLACES
except Exception:
    SHARE_DECIMAL_PLACES = 4
    NAV_DECIMAL_PLACES = 6
    RATE_DECIMAL_PLACES = 6

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def read_fund_capital_changes(conn, ledger_id: Optional[int] = None) -> pd.DataFrame:
    """
    读取资金明细中的本金投入/撤出变动

    规则：
    - 本金投入：发生金额 = +金额（借记金额，投入资金）
    - 本金撤出：发生金额 = -金额（贷记金额，撤回资金）

    Args:
        conn: SQLite 数据库连接
        ledger_id: 账本ID，None 表示全部账本

    Returns:
        pd.DataFrame: 投资本金变动数据
    """
    try:
        query = '''
            SELECT
                ft.id AS 编号,
                ft.date AS 日期,
                ft.type AS 交易类型,
                ft.ledger_id,
                l.name AS 账本名称,
                COALESCE((
                    SELECT SUM(fte.amount_cny)
                    FROM fund_transaction_entries fte
                    WHERE fte.fund_transaction_id = ft.id AND fte.side = 'debit'
                ), 0) AS 借记金额,
                COALESCE((
                    SELECT SUM(fte.amount_cny)
                    FROM fund_transaction_entries fte
                    WHERE fte.fund_transaction_id = ft.id AND fte.side = 'credit'
                ), 0) AS 贷记金额
            FROM fund_transactions ft
            LEFT JOIN ledgers l ON ft.ledger_id = l.id
            WHERE ft.type IN ('本金投入', '本金撤出')
        '''
        params = []
        if ledger_id is not None:
            query += ' AND ft.ledger_id = ?'
            params.append(ledger_id)

        query += ' ORDER BY ft.date ASC, ft.id ASC'

        df = pd.read_sql_query(query, conn, params=params if params else ())

        if df.empty:
            logging.warning("未找到本金投入/撤出记录")
            return pd.DataFrame()

        df['日期'] = pd.to_datetime(df['日期'])

        def calc_amount(row):
            amount = Decimal('0')
            if row.get('交易类型') == '本金投入':
                amount = Decimal(str(row.get('借记金额', 0)))
            elif row.get('交易类型') == '本金撤出':
                amount = -Decimal(str(row.get('贷记金额', 0)))
            return float(amount)

        df['发生金额'] = df.apply(calc_amount, axis=1)
        logging.info(f"读取到 {len(df)} 条本金变动记录")
        return df

    except Exception as e:
        logging.error(f"读取本金变动时发生错误: {e}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame()


def read_daily_account_balance(conn, ledger_id: Optional[int] = None) -> pd.DataFrame:
    """
    读取每日账户余额（按账本汇总，人民币）。
    当日净资产 = 资产类 - 负债类，此处汇总为：资产类账户加、负债类账户减，收入/支出不参与。
    """
    try:
        # 仅汇总资产、负债、权益（balance 已带符号，负债为负）；收入/支出不参与净资产
        query = '''
            SELECT
                abh.date AS 日期,
                a.ledger_id,
                l.name AS 账本名称,
                SUM(CASE
                    WHEN a.type IN ('收入', '支出') THEN 0
                    ELSE abh.balance_cny
                END) AS 账户余额
            FROM account_balance_history abh
            JOIN accounts a ON abh.account_id = a.id
            LEFT JOIN ledgers l ON a.ledger_id = l.id
            WHERE 1=1
        '''
        params = []
        if ledger_id is not None:
            query += ' AND a.ledger_id = ?'
            params.append(ledger_id)

        query += ' GROUP BY abh.date, a.ledger_id, l.name ORDER BY abh.date'

        df = pd.read_sql_query(query, conn, params=params if params else ())

        if df.empty:
            return pd.DataFrame()

        df['日期'] = pd.to_datetime(df['日期'])
        logging.info(f"读取到 {len(df)} 条账户余额记录")
        return df

    except Exception as e:
        logging.error(f"读取账户余额时发生错误: {e}")
        return pd.DataFrame()


def read_daily_position_value(conn, ledger_id: Optional[int] = None) -> pd.DataFrame:
    """
    读取每日持仓市值（按账本汇总，人民币）

    Args:
        conn: SQLite 数据库连接
        ledger_id: 账本ID

    Returns:
        pd.DataFrame: 每日持仓市值汇总
    """
    try:
        query = '''
            SELECT
                date AS 日期,
                ledger_id,
                SUM(market_value_cny) AS 持仓市值
            FROM position_history
            WHERE 1=1
        '''
        params = []
        if ledger_id is not None:
            query += ' AND ledger_id = ?'
            params.append(ledger_id)

        query += ' GROUP BY date, ledger_id ORDER BY date'

        df = pd.read_sql_query(query, conn, params=params if params else ())

        if df.empty:
            return pd.DataFrame()

        df['日期'] = pd.to_datetime(df['日期'])

        # 补充账本名称
        ledgers_df = pd.read_sql_query('SELECT id, name FROM ledgers', conn)
        ledgers_map = dict(zip(ledgers_df['id'], ledgers_df['name']))
        df['账本名称'] = df['ledger_id'].map(ledgers_map)

        logging.info(f"读取到 {len(df)} 条持仓市值记录")
        return df

    except Exception as e:
        logging.error(f"读取持仓市值时发生错误: {e}")
        return pd.DataFrame()


def calculate_return_rate(
    conn,
    ledger_id: int,
    ledger_name: str,
    db=None,
    incremental_from_date: Optional[str] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    计算收益率（净值法）。支持增量：指定 incremental_from_date 时，从该日到昨天重算，前一日的总份额/净值从 return_rate 表读取。

    Args:
        conn: SQLite 数据库连接
        ledger_id: 账本ID
        ledger_name: 账本名称
        db: Database 实例，若提供则用 get_daily_assets 实时计算当日净资产（不依赖快照表）
        incremental_from_date: 增量起始日期 "YYYY-MM-DD"，仅重算该日及之后；若前一日的 return_rate 不存在则退化为全量

    Returns:
        Tuple[pd.DataFrame, pd.DataFrame]: (收益率表数据, 尾差损益数据)
    """
    logging.info(f"开始计算收益率 - 账本: {ledger_name} (id={ledger_id})" + (
        f" 增量从 {incremental_from_date}" if incremental_from_date else ""
    ))

    capital_changes_df = read_fund_capital_changes(conn, ledger_id)
    account_balance_df = read_daily_account_balance(conn, ledger_id)
    position_value_df = read_daily_position_value(conn, ledger_id)

    if capital_changes_df.empty:
        logging.warning(f"账本 {ledger_name} 没有本金投入/撤出记录，无法计算收益率")
        return pd.DataFrame(), pd.DataFrame()

    # 筛选本账本的数据
    capital_changes_df = capital_changes_df[capital_changes_df['ledger_id'] == ledger_id]
    account_balance_df = account_balance_df[account_balance_df['ledger_id'] == ledger_id] if not account_balance_df.empty else pd.DataFrame()
    position_value_df = position_value_df[position_value_df['ledger_id'] == ledger_id] if not position_value_df.empty else pd.DataFrame()

    if capital_changes_df.empty:
        return pd.DataFrame(), pd.DataFrame()

    # 确定日期范围
    min_date = capital_changes_df['日期'].min()
    max_dates = [capital_changes_df['日期'].max()]
    if not account_balance_df.empty:
        max_dates.append(account_balance_df['日期'].max())
    if not position_value_df.empty:
        max_dates.append(position_value_df['日期'].max())
    max_date = max(max_dates)
    yesterday_str = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    # 净值只算到昨天
    end_date_cap = min(pd.Timestamp(max_date), pd.Timestamp(yesterday_str))

    # 增量：从 incremental_from_date 起算，用前一日的 return_rate 做初值
    start_date_for_range = min_date
    total_shares = Decimal('0')
    prev_nav = Decimal('1')
    prev_total_assets = None
    initial_nav = Decimal('1')

    if incremental_from_date:
        prev_d = (datetime.strptime(incremental_from_date, '%Y-%m-%d') - timedelta(days=1)).date()
        prev_date_str = prev_d.strftime('%Y-%m-%d')
        try:
            prev_row = pd.read_sql_query(
                'SELECT 总份额, 单位净值, 当日净资产 FROM return_rate WHERE ledger_id = ? AND date = ?',
                conn, params=[ledger_id, prev_date_str]
            )
            if not prev_row.empty and len(prev_row) > 0:
                row = prev_row.iloc[0]
                total_shares = Decimal(str(row['总份额']))
                prev_nav = Decimal(str(row['单位净值']))
                prev_total_assets = Decimal(str(row['当日净资产']))
                start_date_for_range = incremental_from_date
                logging.info(f"增量计算：从 {incremental_from_date} 起算，前一日的总份额={total_shares} 单位净值={prev_nav}")
            else:
                incremental_from_date = None
        except Exception as e:
            logging.warning(f"读取前一日的 return_rate 失败，退化为全量计算: {e}")
            incremental_from_date = None

    date_range = pd.date_range(start=start_date_for_range, end=end_date_cap, freq='D')

    # 按日期汇总（仅当 db 未提供时用快照表）
    capital_by_date = capital_changes_df.groupby(capital_changes_df['日期'].dt.date)['发生金额'].sum().to_dict()

    if not account_balance_df.empty and db is None:
        balance_by_date = account_balance_df.set_index(account_balance_df['日期'].dt.date)['账户余额'].to_dict()
    else:
        balance_by_date = {}

    if not position_value_df.empty and db is None:
        position_by_date = position_value_df.set_index(position_value_df['日期'].dt.date)['持仓市值'].to_dict()
    else:
        position_by_date = {}

    # 若提供 db，则用实时计算当日净资产（解决快照表缺失时当日净资产为 0 的问题）
    use_realtime_assets = db is not None

    # 汇兑损益暂不支持
    exchange_pl_by_date = {}

    # 计算每日数据
    results = []
    rounding_diffs = []

    for current_date in date_range:
        current_date_key = current_date.date()
        current_date_str = current_date.strftime('%Y-%m-%d')
        prev_total_shares = total_shares

        capital_amount = Decimal(str(capital_by_date.get(current_date_key, 0)))
        if use_realtime_assets and db:
            bal, pos_val = db.get_daily_assets(ledger_id, current_date_str)
            account_balance = Decimal(str(bal))
            position_value = Decimal(str(pos_val))
        else:
            account_balance = Decimal(str(balance_by_date.get(current_date_key, 0)))
            position_value = Decimal(str(position_by_date.get(current_date_key, 0)))
        exchange_pl_amount = Decimal(str(exchange_pl_by_date.get(current_date_key, 0)))

        total_assets = account_balance + position_value + exchange_pl_amount

        if total_shares == Decimal('0'):
            if capital_amount != Decimal('0'):
                nav = initial_nav
                raw_shares = capital_amount / nav
                confirmed_shares = raw_shares.quantize(
                    Decimal(f'0.{"0" * SHARE_DECIMAL_PLACES}'),
                    rounding=ROUND_HALF_UP
                )
                share_diff = raw_shares - confirmed_shares
                if share_diff != Decimal('0'):
                    rounding_amount = share_diff * nav
                    rounding_diffs.append({
                        '日期': current_date_str,
                        '原始份额': float(raw_shares),
                        '确认份额': float(confirmed_shares),
                        '尾差份额': float(share_diff),
                        '尾差金额': float(rounding_amount),
                        '确认净值': float(nav),
                        'ledger_id': ledger_id,
                        '账本': ledger_name,
                        '备注': '份额确认尾差'
                    })

                total_shares = confirmed_shares
                confirm_nav = nav

                results.append({
                    '日期': current_date_str,
                    '发生金额': float(capital_amount),
                    '确认份额': float(confirmed_shares),
                    '确认净值': float(confirm_nav),
                    '总份额': float(total_shares),
                    '单位净值': float(nav),
                    '当日净资产': float(total_assets),
                    '当日损益': 0.0,
                    '当日收益率': '0.00%',
                    '累计收益率': 0.0,
                    '总资产': float(total_assets),
                    'ledger_id': ledger_id,
                    '账本': ledger_name
                })
                prev_nav = nav
                prev_total_assets = total_assets
            else:
                continue
        else:
            if prev_total_shares != Decimal('0'):
                nav = (total_assets - capital_amount) / prev_total_shares
            else:
                nav = prev_nav

            nav = nav.quantize(
                Decimal(f'0.{"0" * NAV_DECIMAL_PLACES}'),
                rounding=ROUND_HALF_UP
            )

            if prev_nav > Decimal('0'):
                daily_return = (nav - prev_nav) / prev_nav
            else:
                daily_return = Decimal('0')

            cumulative_return = (nav - initial_nav) / initial_nav
            confirmed_shares = Decimal('0')
            confirm_nav = nav

            if capital_amount != Decimal('0'):
                raw_shares = capital_amount / nav
                confirmed_shares = raw_shares.quantize(
                    Decimal(f'0.{"0" * SHARE_DECIMAL_PLACES}'),
                    rounding=ROUND_HALF_UP
                )
                share_diff = raw_shares - confirmed_shares
                if share_diff != Decimal('0'):
                    rounding_amount = share_diff * nav
                    rounding_diffs.append({
                        '日期': current_date_str,
                        '原始份额': float(raw_shares),
                        '确认份额': float(confirmed_shares),
                        '尾差份额': float(share_diff),
                        '尾差金额': float(rounding_amount),
                        '确认净值': float(nav),
                        'ledger_id': ledger_id,
                        '账本': ledger_name,
                        '备注': '份额确认尾差'
                    })
                total_shares += confirmed_shares

            if prev_total_assets is not None:
                daily_pnl = total_assets - prev_total_assets - capital_amount
            else:
                daily_pnl = Decimal('0')

            daily_return_pct = f"{float(daily_return) * 100:.2f}%"

            results.append({
                '日期': current_date_str,
                '发生金额': float(capital_amount),
                '确认份额': float(confirmed_shares),
                '确认净值': float(confirm_nav),
                '总份额': float(total_shares),
                '单位净值': float(nav),
                '当日净资产': float(total_assets),
                '当日损益': float(daily_pnl),
                '当日收益率': daily_return_pct,
                '累计收益率': float(cumulative_return),
                '总资产': float(total_assets),
                'ledger_id': ledger_id,
                '账本': ledger_name
            })
            prev_nav = nav
            prev_total_assets = total_assets

    result_df = pd.DataFrame(results)
    rounding_df = pd.DataFrame(rounding_diffs)
    logging.info(f"计算完成，共 {len(result_df)} 条收益率记录，{len(rounding_df)} 条尾差记录")
    return result_df, rounding_df


def generate_return_rate(
    conn,
    ledger_id: Optional[int] = None,
    full_refresh: bool = True,
    write_to_db: bool = True,
    db=None,
    incremental_from_date: Optional[str] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    生成收益率数据的主函数。支持增量：当 incremental_from_date 与 ledger_id 同时指定时，
    仅删除该账本下该日及之后的 return_rate/rounding_diff，并从该日重算到昨天。

    Args:
        conn: SQLite 数据库连接
        ledger_id: 账本ID，None 表示处理所有账本
        full_refresh: 是否全量刷新（增量时仅删除指定日及之后，不删整表）
        write_to_db: 是否写入数据库
        db: Database 实例，用于实时当日净资产
        incremental_from_date: 增量起始日期 "YYYY-MM-DD"，与 ledger_id 同时指定时仅重算该日至今

    Returns:
        Tuple[pd.DataFrame, pd.DataFrame]: (收益率数据, 尾差数据)，多账本时合并
    """
    cursor = conn.cursor()

    # 获取要处理的账本
    if ledger_id is not None:
        cursor.execute('SELECT id, name FROM ledgers WHERE id = ?', (ledger_id,))
        rows = cursor.fetchall()
    else:
        cursor.execute('SELECT id, name FROM ledgers ORDER BY id')
        rows = cursor.fetchall()

    if not rows:
        logging.warning("没有可处理的账本")
        return pd.DataFrame(), pd.DataFrame()

    all_return_df = []
    all_rounding_df = []

    for lid, lname in rows:
        try:
            # 指定了增量起始日期时，对该账本（或全部账本）从该日起重算
            inc_from = incremental_from_date if incremental_from_date else None
            if write_to_db:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='return_rate'")
                if cursor.fetchone():
                    if inc_from:
                        cursor.execute('DELETE FROM return_rate WHERE ledger_id = ? AND date >= ?', (lid, inc_from))
                        cursor.execute('DELETE FROM rounding_diff WHERE ledger_id = ? AND date >= ?', (lid, inc_from))
                        conn.commit()
                    elif full_refresh:
                        cursor.execute('DELETE FROM return_rate WHERE ledger_id = ?', (lid,))
                        cursor.execute('DELETE FROM rounding_diff WHERE ledger_id = ?', (lid,))
                        conn.commit()

            return_df, rounding_df = calculate_return_rate(
                conn, lid, lname, db=db, incremental_from_date=inc_from
            )

            if return_df.empty:
                continue

            if write_to_db and not return_df.empty:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='return_rate'")
                if not cursor.fetchone():
                    logging.warning("return_rate 表不存在，请先启动应用以触发数据库迁移")
                else:
                    for _, row in return_df.iterrows():
                        cursor.execute('''
                            INSERT OR REPLACE INTO return_rate
                            (date, ledger_id, 发生金额, 确认份额, 确认净值, 总份额, 单位净值,
                             当日净资产, 当日损益, 当日收益率, 累计收益率, 总资产, 账本, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                        ''', (
                            row['日期'], row['ledger_id'], row['发生金额'], row['确认份额'],
                            row['确认净值'], row['总份额'], row['单位净值'],
                            row['当日净资产'], row['当日损益'], row['当日收益率'],
                            row['累计收益率'], row['总资产'], row['账本']
                        ))

            if write_to_db and not rounding_df.empty:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='rounding_diff'")
                if cursor.fetchone():
                    for _, row in rounding_df.iterrows():
                        cursor.execute('''
                            INSERT OR REPLACE INTO rounding_diff
                            (date, ledger_id, 原始份额, 确认份额, 尾差份额, 尾差金额, 确认净值, 账本, 备注, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                        ''', (
                            row['日期'], row['ledger_id'], row['原始份额'], row['确认份额'],
                            row['尾差份额'], row['尾差金额'], row['确认净值'],
                            row['账本'], row['备注']
                        ))

            all_return_df.append(return_df)
            all_rounding_df.append(rounding_df)

        except Exception as e:
            logging.error(f"处理账本 {lname} 时发生错误: {e}")
            import traceback
            traceback.print_exc()

    if write_to_db:
        conn.commit()

    result_return = pd.concat(all_return_df, ignore_index=True) if all_return_df else pd.DataFrame()
    result_rounding = pd.concat(all_rounding_df, ignore_index=True) if all_rounding_df else pd.DataFrame()

    return result_return, result_rounding


def get_return_rate_df(conn, ledger_id: Optional[int] = None) -> pd.DataFrame:
    """
    从数据库读取收益率数据

    Args:
        conn: SQLite 数据库连接
        ledger_id: 账本ID，None 表示全部

    Returns:
        pd.DataFrame: 收益率数据
    """
    query = 'SELECT * FROM return_rate WHERE 1=1'
    params = []
    if ledger_id is not None:
        query += ' AND ledger_id = ?'
        params.append(ledger_id)
    query += ' ORDER BY date ASC'
    return pd.read_sql_query(query, conn, params=params if params else ())


if __name__ == "__main__":
    from database import Database
    db = Database()
    return_df, rounding_df = generate_return_rate(db.conn, full_refresh=True, db=db)
    print(f"收益率记录: {len(return_df)} 条")
    print(f"尾差记录: {len(rounding_df)} 条")
    if not return_df.empty:
        print(return_df.tail())
