# 与 GitHub demo-stockpeers 项目对比分析

本文档对比 [Streamlit demo-stockpeers](https://github.com/streamlit/demo-stockpeers/blob/main/streamlit_app.py) 与当前投资财务系统，说明**为何 demo 访问更快**以及**为何 demo 可被安装为网页应用**，并给出可实施的改进建议。

---

## 一、为什么 demo-stockpeers 访问更快？

### 1. 首屏路径更短（无登录、无开场动画）

| 环节 | demo-stockpeers | 当前项目 |
|------|-----------------|----------|
| 开场动画 | 无 | **约 2 秒** 的加载动画（`time.sleep` 循环 + `st.rerun()`） |
| 认证 | 无登录，直接选股票 | 需加载 `config.yaml`、`streamlit-authenticator`、登录/注册 UI |
| 数据依赖 | 选完 ticker 后才调 yfinance | 启动即需 `Database()`、账本/账户列表、侧边栏等 |
| 首屏内容 | 多选 + 时间范围 → 立刻出图 | 登录 → 选账本/账户 → 再进仪表盘 |

demo 的“首屏”只是：多选股票 + 时间范围按钮，**不依赖数据库、不读配置文件、不做认证**，所以脚本执行到第一块可交互 UI 很快。

### 2. 数据加载与缓存策略

**demo-stockpeers：**

```python
@st.cache_resource(show_spinner=False, ttl="6h")
def load_data(tickers, period):
    tickers_obj = yf.Tickers(tickers)
    data = tickers_obj.history(period=period)
    return data["Close"]
```

- 使用 `@st.cache_resource`，**同一 (tickers, period) 在 6 小时内不重复请求**
- 一次请求多只股票，减少网络往返
- `show_spinner=False` 不增加额外转圈

**当前项目：**

- 使用 `@st.cache_data(ttl=300/600)` 缓存账本、账户、组合统计等，已经有助于性能
- 但**每次启动**仍要：读 `config.yaml`、初始化 `Database()`、执行认证逻辑、渲染侧边栏和账本/账户选择，然后才到仪表盘
- 仪表盘内若还有 akshare/数据库查询，首屏仍会受这些 I/O 影响

因此“快”主要差在：**首屏之前要做的事更少**，以及**数据源更单一、缓存更久**。

### 3. 依赖与导入量

- **demo**：streamlit、yfinance、pandas、altair，且无数据库、无认证库。
- **当前项目**：streamlit、streamlit-authenticator、PyYAML、pandas、plotly、akshare、SQLite、多模块（database、crud、analytics、views 等）。

后者在冷启动时导入和初始化更多，首屏时间会相对更长。

---

## 二、为什么 demo 可以“安装为网页应用程序”？

“安装网页应用程序”一般指浏览器/系统的 **“添加到主屏幕”** 或 **“安装应用”**，本质是 **PWA（Progressive Web App）** 的可安装性。

### 1. 可安装性通常需要

- **HTTPS**
- **Web App Manifest**（`manifest.json`）：至少包含 `name`/`short_name`、图标（如 192px、512px）、`start_url`、`display: standalone` 等
- （多数环境下）**Service Worker**，用于离线/安装体验
- 一定的**用户参与度**（如与页面交互约 30 秒后，浏览器才可能显示“安装”）

### 2. demo-stockpeers 为何“能安装”？

- 该 demo 部署在 **Streamlit Community Cloud**（如 `*.streamlit.app`）。
- 云平台在提供 Streamlit 应用时，**可能在同一域名/页面上提供了 manifest 或满足 PWA 的元数据**，因此浏览器会显示“安装”或“添加到主屏幕”。
- 也就是说：**可安装性主要来自部署环境（Streamlit Cloud），而不是 demo 仓库里的 Python 代码本身**。

### 3. 当前项目为何暂时不能安装？

- 项目内**没有** `manifest.json`、**没有** Service Worker、**没有** 任何 PWA 相关配置。
- 若部署在自建环境（如本机 `streamlit run`、自备服务器），通常也未注入 manifest/HTTPS 的完整 PWA 支持。

因此，要像 demo 一样“可安装”，需要：**在提供页面的环境中支持 PWA**（例如使用 Streamlit Cloud，或自建时自己加 manifest + Service Worker + HTTPS）。

---

## 三、可实施的改进建议

### 1. 让“访问更快”

- **缩短或取消固定 2 秒加载动画**  
  - 若保留动画，可改为 0.5 秒或仅首次访问显示；或用 `st.spinner` 替代 `time.sleep` 循环，避免阻塞整 2 秒。
- **延后重量级导入**  
  - 在通过 `query_params` 判断无需展示分享页、且未登录时，尽量不导入 `Database`、`views.dashboard` 等；登录后再 `import` 并创建 `db`。
- **保持并善用缓存**  
  - 继续用 `@st.cache_data` / `@st.cache_resource`，对账本、账户、统计、行情等合理设 TTL；对不常变的数据可适当延长 TTL。
- **首屏优先**  
  - 侧边栏的账本/账户若很多，可考虑默认只取前 N 个或“最近使用”，减少首屏查询量。

### 2. 让应用“可安装”（PWA）

若部署环境是 **Streamlit Community Cloud**：

- 当前 Streamlit 云产品若已支持 PWA，部署上去后即可在浏览器中看到“安装”选项，无需改代码。

若为 **自建部署**（自有服务器、Docker 等）：

- 在**同一域名、HTTPS** 下提供：
  - **Web App Manifest**：  
    在静态目录或通过反向代理提供 `manifest.json`（`name`、`short_name`、`start_url`、`display: "standalone"`、192/512 图标）。
  - **Service Worker**（可选但推荐）：  
    用于缓存静态资源或离线页，满足部分浏览器对“可安装”的更强要求。
- Streamlit 本身不内置 manifest，需通过：
  - 前端注入（若能用自定义 HTML/JS），或
  - Nginx/反向代理在 HTML 里插入 `<link rel="manifest" href="/manifest.json">`，并保证 `manifest.json` 和图标可访问。

参考社区讨论：

- [How to make streamlit app a PWA](https://discuss.streamlit.io/t/how-to-make-streamlit-app-a-pwa/91814)
- [How to link a manifest.json to create a PWA](https://discuss.streamlit.io/t/how-to-link-a-manifest-json-to-create-a-pwa/69682)

---

## 四、小结

| 维度 | demo-stockpeers | 当前项目 |
|------|-----------------|----------|
| 首屏 | 无登录、无长动画，选 ticker 即出图 | 2 秒动画 + 登录 + 账本/账户 + 仪表盘 |
| 数据与缓存 | yfinance + `cache_resource` 6h | DB + 多视图 + `cache_data` 5–10min |
| 可安装为应用 | 部署在 Streamlit Cloud，环境可能带 PWA | 无 manifest/SW，依赖部署方式 |

**访问更快**：主要因为 demo 首屏路径短、无登录、无长动画、数据源单一且缓存久。  
**可安装**：主要因为部署在 Streamlit Cloud 等已支持 PWA 的环境；自建需自行提供 manifest + HTTPS（+ Service Worker）。

按上面“让访问更快”和“让应用可安装”两条线做小幅改造，即可在保留当前功能的前提下，更接近 demo 的体验和可安装性。
