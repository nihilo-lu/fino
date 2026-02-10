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
- **AI 助手**：集成 OpenAI 兼容接口（支持 GPT、MiniMax 等），智能分析投资

## 技术栈

- **后端**：Flask + Python
- **前端**：Vue.js 3 (CDN 引入)
- **数据库**：SQLite (默认)，支持 PostgreSQL、Cloudflare D1
- **数据源**：akshare (获取股票、汇率等数据)

## 快速开始

### 环境要求

- Python 3.8+
- 依赖包：`pip install -r requirements.txt`

### 首次安装

```bash
# 1. 克隆项目
git clone <repository-url>
cd fino

# 2. 安装依赖
pip install -r requirements.txt

# 3. 复制配置文件并修改
cp conf/config.example.yaml conf/config.yaml
# 编辑 conf/config.yaml，根据需要配置数据库、AI 等

# 4. 启动服务
python app.py
```

服务默认运行在 `http://localhost:8086`

### 配置说明

配置文件位于 `conf/config.yaml`，首次使用需复制 `conf/config.example.yaml` 并重命名。主要配置项：

| 配置项 | 说明 |
|--------|------|
| **database** | 数据库配置（SQLite/PostgreSQL/D1） |
| **cookie** | 认证 Cookie 密钥，生产环境务必修改 `key` |
| **credentials** | 用户凭据（用户名、密码哈希） |
| **pre-authorized** | 可注册的邮箱白名单（为空则关闭注册） |
| **ai** | AI 接口配置（支持 OpenAI 格式，兼容 MiniMax 等） |
| **pwa** | PWA 应用名称、图标等 |

### 默认用户

首次运行需通过注册创建用户，或使用预授权邮箱注册。

系统预置默认管理员账户：

| 用户名 | 密码 | 角色 |
|--------|------|------|
| admin | adminadmin | 管理员 |

> 首次登录后建议及时修改默认密码。

## 项目结构

```
fino/
├── app.py                    # Flask 应用入口
├── app/
│   ├── __init__.py           # 应用工厂
│   ├── auth_middleware.py    # 认证中间件
│   ├── config.py             # 配置加载
│   ├── extensions.py         # 扩展初始化
│   ├── utils.py              # 工具函数
│   └── blueprints/           # API 路由模块
│       ├── accounts.py       # 账户
│       ├── ai_chat.py        # AI 聊天
│       ├── analysis.py       # 收益分析
│       ├── auth.py           # 认证
│       ├── fund_transactions.py  # 资金流水
│       ├── ledgers.py        # 账本
│       ├── main.py           # 主路由、静态资源
│       ├── market.py         # 行情、汇率
│       ├── portfolio.py      # 持仓
│       ├── reference.py      # 参考数据
│       └── transactions.py   # 交易
├── conf/
│   ├── config.yaml           # 配置文件（需自行创建）
│   └── config.example.yaml   # 配置模板
├── database.py               # 数据库入口
├── crud_transactions.py      # 交易 CRUD
├── analytics.py              # 收益分析
├── return_rate_sqlite.py     # 收益率计算
├── helpers.py                # 辅助函数
├── frontend/
│   ├── index.html            # HTML 入口
│   ├── css/styles.css        # 样式
│   ├── js/
│   │   ├── app.js            # 前端入口
│   │   └── vue/              # Vue 组件
│   ├── icons/                # PWA 图标
│   ├── manifest.json         # PWA 配置
│   └── sw.js                 # Service Worker
├── scripts/
│   └── generate_pwa_icons.py # PWA 图标生成
├── utils/                    # 工具模块
│   ├── auth_config.py        # 认证配置
│   ├── cache_utils.py        # 缓存
│   ├── db_*.py               # 各数据库实现
│   ├── fifo_framework.py     # FIFO 成本法
│   ├── wac_framework.py      # WAC 成本法
│   └── get_market_price.py   # 行情获取
├── docs/                     # 文档
├── requirements.txt          # Python 依赖
└── investment.db             # SQLite 数据库（使用 SQLite 时生成）
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
| POST | /api/auth/login | 登录 |
| POST | /api/auth/logout | 退出 |
| GET | /api/auth/me | 获取当前用户 |
| PUT | /api/auth/profile | 更新个人资料 |
| PUT | /api/auth/password | 修改密码 |
| POST | /api/auth/avatar | 上传头像 |
| POST | /api/auth/register | 注册 |
| GET | /api/auth/users | 获取用户列表（管理员） |
| POST | /api/auth/users | 创建用户（管理员） |
| PUT | /api/auth/users/:username | 更新用户（管理员） |
| DELETE | /api/auth/users/:username | 删除用户（管理员） |

### 账本接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/ledgers | 获取账本列表 |
| POST | /api/ledgers | 创建账本 |
| DELETE | /api/ledgers/:id | 删除账本 |

### 账户接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/accounts | 获取账户列表 |
| POST | /api/accounts | 创建账户 |
| DELETE | /api/accounts/:id | 删除账户 |

### 交易接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/transactions | 获取交易列表 |
| POST | /api/transactions | 创建交易 |
| DELETE | /api/transactions/:id | 删除交易 |

### 持仓接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/positions | 获取持仓列表 |
| DELETE | /api/positions/:id | 删除持仓 |

### 资金流水接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/fund-transactions | 获取资金流水 |
| POST | /api/fund-transactions | 创建资金流水 |

### 收益分析接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/analysis/returns | 收益率分析 |

### 参考数据接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/categories | 获取投资类别 |
| GET | /api/currencies | 获取币种列表 |

### 行情接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/market/price | 获取行情价格 |
| POST | /api/exchange-rate | 获取汇率 |

### 组合接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/portfolio/stats | 组合统计 |
| GET | /api/portfolio/positions | 持仓列表 |

### AI 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/ai/config | 获取 AI 配置 |
| PUT | /api/ai/config | 更新 AI 配置 |
| POST | /api/ai/chat | AI 对话 |

### 系统接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/health | 健康检查 |
| GET | /api/pwa/config | 获取 PWA 配置 |
| GET | /api/database/config | 获取数据库配置 |

## 文档索引

| 文档 | 说明 |
|------|------|
| [数据库结构与关联关系说明](docs/数据库结构与关联关系说明.md) | 数据表设计 |
| [多数据库架构说明](docs/多数据库架构说明.md) | 多数据库支持 |
| [用户认证与权限说明](docs/用户认证与权限说明.md) | 登录、注册、权限 |
| [缓存实现说明](docs/缓存实现说明.md) | 缓存机制 |
| [数据更新逻辑](docs/数据更新逻辑.md) | 数据更新流程 |

## 开发说明

### 新增数据库支持

1. 在 `utils/` 下创建 `db_xxx_manager.py`
2. 实现 `DBManagerBase` 协议
3. 在 `utils/db_base.py` 注册

详见 [docs/多数据库架构说明.md](docs/多数据库架构说明.md)

### 添加新功能

1. 后端：在 `app/blueprints/` 添加蓝图或扩展现有蓝图
2. 前端：在 `frontend/js/vue/` 添加 Vue 组件
3. API：遵循 RESTful 风格

### 端口配置

默认端口为 8086，可在 `app.py` 中修改 `app.run(port=...)`。

## License

MIT
