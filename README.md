# 投资追踪器

一个投资组合追踪与收益分析工具，支持多账户、多币种、持仓管理和收益计算。

## 功能特性

- **多账户管理**：支持银行账户、券商账户等多种账户类型
- **交易记录**：记录买入、卖出、分红等各类交易
- **持仓追踪**：自动计算持仓成本和当前市值
- **收益分析**：支持 FIFO 和 WAC 成本法，计算收益率
- **多币种支持**：自动获取汇率，转换为人民币统计
- **资金流水**：借贷记账法记录资金变动
- **PWA 支持**：可安装到桌面/手机使用
- **AI 助手**：集成 MiniMax 模型，智能分析投资

## 技术栈

- **后端**：Flask + Python
- **前端**：Vue.js 3 (CDN 引入)
- **数据库**：SQLite (默认)，支持 PostgreSQL、Cloudflare D1
- **数据源**：akshare (获取股票、汇率等数据)

## 快速开始

### 环境要求

- Python 3.8+
- 依赖包：`pip install -r requirements.txt`

### 启动服务

```bash
python app.py
```

服务默认运行在 `http://localhost:8085`

### 配置说明

配置文件位于 `conf/config.yaml`，包含：

- **database**：数据库配置（SQLite/PostgreSQL/D1）
- **cookie**：认证 Cookie 设置
- **credentials**：用户凭据
- **pwa**：PWA 应用配置
- **ai**：AI 接口配置

### 默认用户

| 用户名 | 密码 |
|--------|------|
| nihilo | nihilo_lu |

## 项目结构

```
fino/
├── app.py                 # Flask 应用入口
├── app/
│   ├── __init__.py        # 应用工厂
│   ├── auth_middleware.py # 认证中间件
│   ├── config.py          # 配置加载
│   ├── extensions.py      # 扩展初始化
│   └── utils.py           # 工具函数
├── conf/
│   ├── config.yaml        # 配置文件
│   └── config.example.yaml
├── database.py            # 数据库入口
├── crud_transactions.py   # 交易 CRUD
├── analytics.py           # 收益分析
├── return_rate_sqlite.py  # 收益率计算
├── frontend/
│   ├── index.html         # HTML 入口
│   ├── css/styles.css     # 样式
│   ├── js/
│   │   ├── app.js         # 前端入口
│   │   └── vue/           # Vue 组件
│   ├── icons/             # PWA 图标
│   ├── manifest.json      # PWA 配置
│   └── sw.js              # Service Worker
├── docs/                  # 文档
├── requirements.txt      # Python 依赖
└── investment.db          # SQLite 数据库
```

## 数据库设计

核心数据表：

| 表名 | 说明 |
|------|------|
| `ledgers` | 账本，按用户隔离 |
| `accounts` | 账户（银行/券商等） |
| `categories` | 投资类别 |
| `currencies` | 币种与汇率 |
| `transactions` | 交易记录 |
| `positions` | 持仓快照 |
| `fund_transactions` | 资金明细主表 |
| `fund_transaction_entries` | 资金分录表 |

详见 [docs/数据库结构与关联关系说明.md](docs/数据库结构与关联关系说明.md)

## 多数据库支持

支持三种数据库后端，通过 `conf/config.yaml` 配置：

- **SQLite**：默认，无需额外配置
- **PostgreSQL**：需安装 `psycopg2-binary`，配置连接参数
- **Cloudflare D1**：通过 HTTP API 连接

详见 [docs/多数据库架构说明.md](docs/多数据库架构说明.md)

## API 文档

### 认证接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/login | 登录 |
| POST | /api/logout | 退出 |

### 账本接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/ledgers | 获取账本列表 |
| POST | /api/ledgers | 创建账本 |

### 账户接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/accounts | 获取账户列表 |
| POST | /api/accounts | 创建账户 |

### 交易接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/transactions | 获取交易列表 |
| POST | /api/transactions | 创建交易 |
| PUT | /api/transactions/:id | 更新交易 |
| DELETE | /api/transactions/:id | 删除交易 |

### 持仓接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/positions | 获取持仓列表 |
| PUT | /api/positions/:id | 更新持仓 |

### 收益分析接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/analytics/return-rate | 收益率分析 |
| GET | /api/analytics/summary | 收益汇总 |

## 开发说明

### 新增数据库支持

1. 在 `utils/` 下创建 `db_xxx_manager.py`
2. 实现 `DBManagerBase` 协议
3. 在 `utils/db_base.py` 注册

详见 [docs/多数据库架构说明.md](docs/多数据库架构说明.md)

### 添加新功能

1. 后端：在 `app/` 或根目录添加业务逻辑
2. 前端：在 `frontend/js/vue/` 添加 Vue 组件
3. API：遵循 RESTful 风格

## License

MIT
