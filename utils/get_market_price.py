import akshare as ak
import pandas as pd
import logging

# 本脚本获取价格信息，输出的列为日期、代码、、币种

import pandas as pd

def supplementary_holidays_data(df, start_date, end_date, date_column="日期", value_columns=["收盘", "币种"]):
    """
    填充 DataFrame 中缺失的日期（周末和节假日），并使用前一个有效值填充缺失值。

    Args:
        df (pandas.DataFrame): 包含日期和值的 DataFrame。
        start_date (str): 开始日期，格式为 "YYYY-MM-DD"。
        end_date (str): 结束日期，格式为 "YYYY-MM-DD"。
        date_column (str): 日期列的名称 (默认为 "日期")
        value_columns (list): 需要填充的value列的名称列表（默认为 ["收盘", "币种"]）

    Returns:
        pandas.DataFrame: 填充后的 DataFrame。
    """
    date_range = pd.date_range(start=start_date, end=end_date)
    final_df = pd.DataFrame({date_column: date_range})
    final_df[date_column] = final_df[date_column].dt.strftime("%Y-%m-%d")  # 转换为字符串格式

    df = df.copy()  # 创建 DataFrame 的副本，避免修改原始数据

    # 确保日期列为字符串类型，方便join
    try:
        df[date_column] = df[date_column].astype(str)
    except Exception as e:
        raise ValueError(f"无法将 '{date_column}' 列转换为字符串：{e}")

    # 检查数据类型是否一致
    if df[date_column].dtype != final_df[date_column].dtype:
        print(f"df['{date_column}'] 的类型: {df[date_column].dtype}")
        print(f"final_df['{date_column}'] 的类型: {final_df[date_column].dtype}")
        raise TypeError(f"'{date_column}' 列在两个 DataFrame 中的数据类型不匹配。")

    final_df = pd.merge(final_df, df, on=date_column, how="left")

    for col in value_columns:
        if col in final_df.columns:  # 检查列是否存在
            final_df[col] = final_df[col].ffill()  # 使用前一个有效值填充 NaN

    return final_df



# 获取股票价格，输出的列为：日期、类型、代码、价格、币种
def get_stock_close_price(stock_code, start_date, end_date, market):
    """
    获取指定股票在指定日期范围内的不复权收盘价和日期，支持 A 股、港股和美股。
    如果日期范围包含周末和节假日，但获取到的数据不包含周末和节假日，
    则在周末和节假日引用最后一个工作日的数据。

    Args:
        stock_code (str): 股票代码，例如 "600519" (A股), "00700" (港股), "AAPL" (美股)。
        start_date (str): 开始日期，格式为 "YYYY-MM-DD"。
        end_date (str): 结束日期，格式为 "YYYY-MM-DD"。
        market (str): 市场类型，"A" (A股，默认), "HK" (港股), "US" (美股)。

    Returns:
        pandas.DataFrame: 包含 "日期" 和 "价格" 两列的 DataFrame，如果没有数据，则返回 None。
    """
    try:
        if market == "A" or market == "SH" or market == "SZ" or market == "BJ":
            # 转换日期格式
            start_date_ak = start_date.replace("-", "")
            end_date_ak = end_date.replace("-", "")
            
            # 获取数据
            df = ak.stock_zh_a_hist(symbol=stock_code, period="daily", start_date=start_date_ak, end_date=end_date_ak)

            # 判断数据是否为空
            if df is None or len(df) == 0:
                return None
            else:
            # 筛选数据
                close_prices = df[["日期", "收盘"]].copy()  # 创建副本，避免修改原始数据
                
            # 处理周末和节假日
                close_prices = supplementary_holidays_data(close_prices, start_date, end_date,date_column="日期",value_columns=["收盘"])

            # 对列进行创建、重命名和排序
                close_prices.rename(columns={"收盘": "价格"}, inplace=True)
                new_stock_code = market+"."+stock_code
                close_prices.loc[:, '代码'] = new_stock_code
                close_prices.loc[:, '类型'] = "股票"
                close_prices.loc[:, '币种'] = "CNY" # 使用 .loc 设置值
                close_prices = close_prices.reindex(columns=["日期","类型","代码","价格","币种"])


        elif market == "HK":
            # 转换日期格式
            start_date_ak = start_date.replace("-", "")
            end_date_ak = end_date.replace("-", "")
            
             # 获取数据
            df = ak.stock_hk_hist(symbol=stock_code, period="daily", start_date=start_date_ak, end_date=end_date_ak)
            
            # 判断数据是否为空
            if df is None or len(df) == 0:
                return None
            else:
            # 筛选数据
                close_prices = df[["日期", "收盘"]].copy()  # 创建副本，避免修改原始数据

             # 处理周末和节假日
                close_prices = supplementary_holidays_data(close_prices, start_date, end_date,date_column="日期",value_columns=["收盘"])

            # 对列进行创建、重命名和排序
                close_prices.rename(columns={"收盘": "价格"}, inplace=True)
                new_stock_code = market+"."+stock_code
                close_prices.loc[:, '代码'] = new_stock_code
                close_prices.loc[:, '类型'] = "股票"
                close_prices.loc[:, '币种'] = "HKD" # 使用 .loc 设置值
                close_prices = close_prices.reindex(columns=["日期","类型","代码","价格","币种"])

            
        elif market == "US":
            # 获取数据
            df = ak.stock_us_daily(symbol=stock_code, adjust="")    #采用新浪数据
            

            # 判断数据是否为空
            if df is None or len(df) == 0:
                logging.info("⚠️查询外汇数据结果为空！")    
                return None
            else:
            # 筛选数据
                df = df[(df['date'] >= start_date) & (df['date'] <= end_date)]
                close_prices = df[["date", "close"]].copy()  # 创建副本，避免修改原始数据



            # 处理周末和节假日
                close_prices = supplementary_holidays_data(close_prices, start_date, end_date,date_column="date",value_columns=["close"])
            
            # 对列进行新建、重命名和排序
                close_prices.rename(columns={"date": "日期","close":"价格"}, inplace=True)
                new_stock_code = market+"."+stock_code
                close_prices.loc[:, '代码'] = new_stock_code
                close_prices.loc[:, '币种'] = "USD" # 使用 .loc 设置值
                close_prices.loc[:, '类型'] = "股票"
                close_prices = close_prices.reindex(columns=["日期","类型","代码","价格","币种"])


        else:
            logging.info("⚠️不支持的市场类型，请选择 'A', 'HK' 或 'US'")
            return pd.DataFrame()

    except Exception as e:
        logging.error(f"❌获取股票数据时发生错误: {e}")
        return False
    
    else:
        logging.info("✅获取股票价格信息完成！")
        return close_prices


# 获取外汇价格，输出的列为：日期、类型、币种、价格
def get_Settlement_exchange_rate(type,symbol,start_date, end_date):
    '''
    type参数介绍：
        中行汇买价：这是银行从你手中买入外币时使用的价格。
        中行钞卖价/汇卖价：这是银行向你卖出外币时使用的价格。如果你要用人民币去购买外币，银行是“卖出”外币给你，这时你会参考汇卖价。
        央行中间价：中间价是买入价（汇买价）和卖出价（汇卖价）的平均值。
    '''
    try:
        # 转换日期格式
        start_date_ak = start_date.replace("-", "")
        end_date_ak = end_date.replace("-", "")

        # 定义货币映射
        currency_map = {
            "HKD": "港币",
            "USD": "美元",
            "EUR": "欧元",
            "GBP": "英镑",
            "JPY": "日元",
            "AUD": "澳元",
            "CAD": "加元",
            "CHF": "瑞士法郎",
            "CNY": "人民币",
        }
        new_symbol = currency_map.get(symbol, symbol) # 如果找不到，则返回第原始符号（第二个symbol）

        # 获取价格信息
        currency_boc_sina_df = ak.currency_boc_sina(new_symbol,start_date_ak, end_date_ak)
        
        # 判断数据是否为空
        if currency_boc_sina_df.empty:
            logging.info("⚠️外汇牌价查询结果为空！")
            return pd.DataFrame()
        else:
        # 筛选数据
            exchange_rate = currency_boc_sina_df.loc[:, ['日期', type]].copy() # 只保留指定列,并创建副本
        
        # 处理周末和节假日，需要指定value_columns为type和“币种”
            exchange_rate = supplementary_holidays_data(exchange_rate, start_date, end_date, value_columns=[type, "币种"])
            
        # 对列进行新建、修改、重命名和排序
            exchange_rate.rename(columns={type: "价格"}, inplace=True)
            exchange_rate.loc[:, '代码'] = symbol # 使用 .loc 新增列
            exchange_rate.loc[:, '币种'] = "CNY" # 使用 .loc 新增列
            exchange_rate.loc[:, "价格"] = exchange_rate["价格"] * 0.01 
            exchange_rate.loc[:, '类型'] = "外汇"
            exchange_rate = exchange_rate.reindex(columns=["日期","类型","代码","价格","币种"])
            logging.info("✅外汇价格查询成功！")
            return exchange_rate

    except Exception as e:
        logging.error(f"❌获取汇率数据时发生错误: {e}")
        return False


def get_stock_close_price_range(full_code: str, start_date: str, end_date: str):
    """
    按日期范围获取证券历史收盘价（供历史价格功能使用）。
    支持代码格式：市场.代码，如 HK.00700、SH.600519、US.AAPL；无前缀默认为 A 股。

    Args:
        full_code: 完整代码，如 "HK.00700"
        start_date: 开始日期 "YYYY-MM-DD"
        end_date: 结束日期 "YYYY-MM-DD"

    Returns:
        pandas.DataFrame: 列 ["日期", "代码", "价格"]，无数据或失败返回 None/空 DataFrame。
    """
    separator = "."
    skip_separator = "-"
    if skip_separator in full_code:
        logging.info(f"⚠️ 代码包含跳过符号 '{skip_separator}'，跳过价格请求: {full_code}")
        return None
    if separator in full_code:
        market, stock_code = full_code.split(separator, 1)
    else:
        market = "A"
        stock_code = full_code
    result = get_stock_close_price(stock_code, start_date, end_date, market)
    if result is None or (isinstance(result, pd.DataFrame) and result.empty) or result is False:
        return None
    return result[["日期", "代码", "价格"]].copy()


def get_exchange_rate_range(currency_code: str, start_date: str, end_date: str):
    """
    按日期范围获取外汇历史汇率（相对人民币，供历史价格功能使用）。
    使用中行汇买价。

    Args:
        currency_code: 币种代码，如 "USD", "HKD"
        start_date: 开始日期 "YYYY-MM-DD"
        end_date: 结束日期 "YYYY-MM-DD"

    Returns:
        pandas.DataFrame: 列 ["日期", "代码", "价格"]（价格为相对人民币汇率），无数据或失败返回 None/空 DataFrame。
    """
    if currency_code == "CNY":
        date_range = pd.date_range(start=start_date, end=end_date)
        return pd.DataFrame({
            "日期": date_range.strftime("%Y-%m-%d"),
            "代码": "CNY",
            "价格": 1.0,
        })
    result = get_Settlement_exchange_rate("中行汇买价", currency_code, start_date, end_date)
    if result is None or (isinstance(result, pd.DataFrame) and result.empty) or result is False:
        return None
    return result[["日期", "代码", "价格"]].copy()


if __name__ == "__main__":
    # 示例用法
    full_stock_code = "HK.00881"  # 示例完整股票代码（市场.代码）
    start_date = "2025-02-07"
    end_date = "2025-02-07"
    
    # 配置参数
    separator = "."  # 市场和代码之间的分隔符
    skip_separator = "-"  # 如果代码包含此符号，则跳过请求价格

    # 检查是否包含跳过符号
    if skip_separator in full_stock_code:
        print(f"⚠️ 代码包含跳过符号 '{skip_separator}'，跳过价格请求: {full_stock_code}")
    else:
        # 拆分市场类型和股票代码
        if separator in full_stock_code:
            market, stock_code = full_stock_code.split(separator, 1)  # 使用分隔符拆分，1 表示只拆分一次
        else:
            # 如果没有市场前缀，默认为A股
            market = "A"
            stock_code = full_stock_code
        
        print(f"市场类型: {market}, 股票代码: {stock_code}")
        
        # 使用拆分后的市场和代码获取价格
        result = get_stock_close_price(stock_code, start_date, end_date, market)
        print(result)
    
    # 外汇价格查询示例
    # print(get_Settlement_exchange_rate("中行汇买价","HKD",start_date,end_date))
    
    # 更多测试示例：
    # full_stock_code = "US.AAPL"  # 美股示例
    # full_stock_code = "SH.600519"  # 沪市示例
    # full_stock_code = "600519"  # 无市场前缀示例
    # full_stock_code = "HK-00881"  # 包含"-"符号，会跳过价格请求
