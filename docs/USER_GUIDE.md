# AlphaOps Workbench 用户使用说明

本说明面向在 Windows 本地运行 AlphaOps Workbench 的量化用户。

## 安装

在项目目录打开 PowerShell：

```powershell
cd <你的 AlphaOps Workbench 项目目录>
scripts/windows/install.ps1
```

如果已经有构建好的 wheel 包：

```powershell
scripts/windows/install-from-wheel.ps1
```

## 初始化本地存储

```powershell
scripts/windows/init.ps1
```

这会创建本地 DuckDB schema。初始化只负责建库，不会自动把真实行情写进去。

## 配置本地 API Key

推荐使用本地密钥配置脚本。它会把 key 写入项目根目录的 `.env`；该文件已被 Git 忽略，不会进入公开发布包：

```powershell
scripts/windows/configure-local-secrets.ps1 -MassiveApiKey "你的 Massive API key"
```

只安装 wheel 的用户可以使用统一 CLI：

```powershell
alphaops configure --massive-api-key "你的 Massive API key"
```

需要切换为其他人的 key 时，再运行一次同一命令即可。公开版本只保留空白 `.env.example` 和此配置入口，不包含任何真实 key。

从项目目录运行 `alphaops` 或 Windows 启动脚本时，程序会自动读取项目根目录 `.env`。需要从其他目录启动时，可以设置 `ALPHAOPS_ENV_FILE` 指向该本地密钥文件。

## 启动工作台

```powershell
scripts/windows/start-ui.ps1
```

打开终端显示的 Streamlit 地址。浏览器里的 Streamlit 工作台才是主产品界面，命令行只负责安装、初始化、启动和 smoke check。

## 数据接入

进入“数据中心”页面后可以使用三类入口。

### 公开美股数据

使用“公开美股数据接入”区域：

- 数据源优先选择 `massive`；`yfinance` 作为无需 key 的备用入口；`alpaca` 入口保留但当前不作为默认路径。
- 输入标的代码，例如 `NVDA,MSFT,AAPL`。
- 输入开始和结束日期。
- 选择频率：`1d`、`1wk` 或 `1mo`。
- 点击对应的拉取按钮。

Massive 需要 API key。设置方式：

```powershell
$env:MASSIVE_API_KEY="你的 Massive API key"
```

设置后可以在浏览器工作台使用，也可以直接通过 CLI 拉取并写入 DuckDB：

```powershell
alphaops massive-fetch --symbols NVDA,MSFT --start 2026-05-28 --end 2026-06-03 --frequency 1d
```

yfinance 不需要 key，但上游可能限流。Alpaca 需要你登录 Alpaca Dashboard，在 API Keys 页面生成 Market Data 可用的 key id 和 secret，然后设置环境变量：

```powershell
$env:ALPACA_API_KEY_ID="你的 Alpaca key id"
$env:ALPACA_API_SECRET_KEY="你的 Alpaca secret"
$env:ALPACA_DATA_FEED="iex"
```

`iex` 通常适合基础/免费实时美股行情。`sip`、`delayed_sip` 等 feed 取决于你的 Alpaca 数据订阅权限。

设置后有两种使用方式：

1. 浏览器工作台历史行情入库：进入“数据中心”，在“公开美股数据接入”里把数据源切换为 `alpaca`，选择 feed、标的、日期和频率，点击“拉取 Alpaca 行情”。数据会写入 DuckDB，并进入 Lineage 和 Data Quality 流程。
2. 实时 trades 验证：在 PowerShell 中运行：

```powershell
alphaops alpaca-stream --symbols NVDA,MSFT --seconds 15 --feed iex
```

这个命令会连接 Alpaca 实时股票数据 WebSocket，打印收到的逐笔成交。它只用于验证本地实时连接；研究数据入库仍建议先通过“数据中心”写入结构化 market_bars。

Alpaca crypto 行情可以用下面的命令验证：

```powershell
alphaops alpaca-crypto-bars --symbols BTC/USD --start 2026-05-28 --end 2026-06-03
```

当前核心研究数据契约仍是 equity、ETF、futures。Crypto 命令是行情可用性验证入口，暂不写入 `market_bars`。

### 本地私有 CSV/Parquet

使用“本地私有数据接入”区域：

- 可以直接填写本地文件路径，也可以上传 CSV/Parquet。
- 选择资产类型：`equity`、`etf` 或 `futures`。
- 输入标的代码；留空表示读取文件中全部标的。
- 输入日期范围和频率。
- 点击“导入私有文件”。

CSV/Parquet 至少需要这些字段，或使用右侧别名：

```text
symbol/ticker
timestamp/trade_date
open/open_px
high/high_px
low/low_px
close/close_px
volume/vol
```

期货数据还需要：

```text
contract_id
```

本地 CSV/Parquet 文件通过 Private Data Ingestion Adapter 导入，并进入与公共数据源相同的 Data Contract、Lineage、Quality 流程。

### 体验流程样本数据

如果只是想先看看页面如何联动，可以点击“写入样本数据”。这些数据只用于熟悉流程，不可用于研究结论。

## 推荐研究流程

1. 在“数据中心”拉取公开美股数据，或导入本地 CSV/Parquet 私有数据。
2. 在“数据质量”生成质量报告，确认缺失、重复、价格区间、覆盖缺口等问题。
3. 在“Alpha 工厂”输入 Alpha DSL 公式，例如 `rank(close)`，创建候选 Alpha。
4. 在“回测实验室”配置 Backtest Contract、成本模型、Benchmark 和组合约束。
5. 在“风险监控”运行风险评审。
6. 在“Alpha 注册表”查看生命周期、指标、风险标记和报告链接。
7. 在“报告中心”生成 Markdown/HTML 研究报告。
8. 在“评估仪表盘”运行内置 evaluation cases。

## 期货数据需要你准备什么

当前本地可用路径是 CSV/Parquet 私有数据接入。你需要提供包含期货行情和 `contract_id` 的文件。

后续如果要接 Databento、IBKR 或其他期货源，需要提供：

- 数据供应商名称。
- API key 或登录方式，必须放环境变量，不写入代码。
- 合约范围，例如 CME MNQ、ES、NQ。
- 是否需要连续合约、展期规则、夜盘交易时段。

## Smoke Check

```powershell
scripts/windows/smoke.ps1
```

smoke 会跑真实产品路径：数据质量、Alpha 工厂、回测实验室、合成指数实验室、风险监控、报告中心和评估仪表盘。

## English Product Page Names

The implemented product pages are: Data Hub, Data Quality, Synthetic Index Lab, Alpha Factory, Backtest Lab, Alpha Registry, Risk Monitor, Agent Console, Report Center, Connector Admin, and Evaluation Dashboard.

OpenRouter is only the LLM gateway. Private Data Ingestion Adapter is the local CSV/Parquet ingestion path.
