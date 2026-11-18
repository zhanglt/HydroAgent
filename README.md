# HydroAgent - 智能灌溉决策与运营系统

HydroAgent 是一个面向农业灌溉场景的智能决策与运营管理系统。系统以后端 FastAPI 服务为核心，结合分区化灌溉计划、审批执行链路、传感器与天气数据处理、告警审计、报表、知识库和 LLM 智能对话能力，并提供基于 Next.js 的 Web 控制台。

系统围绕“感知数据、风险评估、计划生成、人工审批、安全执行、过程审计、可视化运营”构建完整闭环。灌溉启动必须基于结构化计划和审批记录，天气风险、传感器异常、执行器不可用等情况会进入暂缓或风险提示路径，避免未经确认的自动执行。

## 主要功能

- **分区化灌溉管理**：按区域维护作物阈值、传感器、执行器、默认灌溉时长和运行状态。
- **智能计划生成**：根据土壤湿度、天气风险、区域配置和历史记录生成结构化灌溉计划。
- **审批与执行闭环**：支持计划审批、拒绝、执行、停止、手动覆盖和执行结果记录。
- **安全策略约束**：对降雨风险、传感器异常、执行器不可用、重复执行等情况进行风险控制。
- **数据处理与预测**：提供传感器数据采集、天气数据处理、土壤湿度预测和区域状态分析能力。
- **AI 对话与工具调用**：通过 LLM 智能体、MCP 工具和持久化会话支持自然语言查询、计划生成和过程追踪。
- **运营管理后台**：包含资产、告警、用户、角色权限、知识库、报表、历史记录和系统设置。
- **Web 控制台**：使用 Next.js、React 和 TypeScript 构建统一的运营界面。

## 技术栈

- **后端**：Python、FastAPI、SQLAlchemy、SQLite / PostgreSQL / MySQL、LangChain、FastMCP、OpenAI SDK。
- **前端**：Next.js、React、TypeScript、Tailwind CSS、ECharts。
- **存储**：SQLAlchemy 负责业务数据；LangGraph SQLite persistence 负责对话与工具调用轨迹；Chroma 支持知识库向量检索。
- **部署**：支持本地脚本、Dockerfile 和 Docker Compose。

## 目录结构

```text
.
├── src/                    # 后端服务源码
│   ├── main.py             # FastAPI 应用入口
│   ├── api.py              # 核心 API 路由
│   ├── config/             # 配置加载与持久化
│   ├── database/           # 数据模型和数据库初始化
│   ├── services/           # 灌溉、资产、告警、认证、RBAC、报表等业务服务
│   ├── data/               # 传感器采集与天气数据处理
│   ├── llm/                # 智能体、工具解析、对话持久化
│   ├── knowledge/          # 知识库文档与检索服务
│   ├── ml/                 # 土壤湿度预测相关模块
│   └── control/            # 执行器控制相关模块
├── frontend/               # Next.js 前端控制台
├── tests/                  # 后端测试
├── config.template.yaml    # 配置模板
├── requirements.txt        # 后端依赖
├── start.sh                # 本地统一启动脚本
├── start-backend.sh        # 后端启动脚本
├── start-frontend.sh       # 前端启动脚本
└── docker-compose.yml      # 容器编排配置
```

## 环境要求

- Python 3.11 或更高版本，推荐 Python 3.12。
- Node.js 20 或更高版本。
- npm 10 或更高版本。
- 可选：Docker 与 Docker Compose。

默认数据库为 SQLite，无需额外安装数据库服务。如需使用 PostgreSQL 或 MySQL，可在 `config.yaml` 中配置数据库连接。

## 安装与配置

### 1. 克隆项目

```bash
git clone https://github.com/nullskymc/HydroAgent.git
cd HydroAgent
```

如果使用已有本地仓库，直接进入项目根目录即可。

### 2. 创建配置文件

```bash
cp config.template.yaml config.yaml
```

根据实际环境修改 `config.yaml`：

```yaml
openai_api_key: sk-xxx-your-openai-key
openai_base_url: https://your-openai-base-url/v1
openai_wire_api: auto
model_name: gpt-4o
embedding_model_name: text-embedding-3-small
embedding_base_url: ""  # 单独指定向量服务地址，留空复用 openai_base_url

apis:
  weather_service_url: "https://api.open-meteo.com/v1/forecast"
```

常用配置项：

- `openai_api_key`：LLM 与知识库能力使用的 API Key。
- `openai_base_url`：OpenAI 兼容接口地址。
- `openai_wire_api`：聊天协议，支持 `auto`（默认）、`responses`、`chat_completions`。设置页“聊天 API 协议”可修改并热重载；不影响 Embeddings 接口。
- `model_name`：智能体对话和计划生成使用的模型。
- `embedding_model_name`：知识库向量化使用的模型。
- `embedding_base_url`：独立的向量服务基础 URL；未配置或留空时复用 `openai_base_url`。设置页“知识引擎”可修改，Embeddings 模型列表也使用该地址和对应的向量 API Key。
- `apis.weather_service_url`：天气预报服务地址。
- `proxy`：`api.open-meteo.com` 天气预报请求使用的代理，例如 `http://10.0.0.8:30000`；未配置或为空时沿用 Requests 的默认网络行为。此配置不修改聊天、Embeddings、自定义天气地址或地理编码请求的代理。
- `database`：数据库配置；未配置时使用本地 SQLite。

Open-Meteo 直连超时的环境，可在 `config.yaml` 顶层配置并重启后端：

```yaml
proxy: http://10.0.0.8:30000
```

如果第三方服务在 Codex 中配置 `wire_api = "responses"`，本项目对应配置为：

```yaml
openai_base_url: https://gateway.example/openai
openai_wire_api: responses
model_name: gpt-6.1-sol
```

以上域名为占位示例，实际服务地址仅填写在本地私有 `config.yaml`，不要写入待提交的文档或日志。`openai_base_url` 保留服务商给出的基础地址，不追加 `/responses`；SDK 根据协议追加路径。Responses 模式使用流式请求，并将系统指令的出站角色映射为 `developer`，兼容拒绝 `system` 角色的网关。Chat Completions 模式继续保留原消息格式与 DeepSeek 推理字段。故障原因和验证见[第三方 Responses 400 修复记录](docs/fix-responses-gateway-400.md)。

生产或多人环境建议在 `config.yaml` 中直接配置 API Key，也可通过环境变量覆盖：

```bash
export OPENAI_API_KEY="sk-xxx"           # 覆盖 config.yaml 中的 openai_api_key
export HYDROAUTH_SECRET="change-this-auth-secret"
```

### 3. 一键启动

项目提供统一启动脚本，会自动创建 Python 虚拟环境、安装缺失依赖，并启动后端和前端：

```bash
./start.sh
```

默认访问地址：

- 后端 API：`http://127.0.0.1:7860`
- 后端健康检查：`http://127.0.0.1:7860/api/health`
- 前端控制台：`http://127.0.0.1:3000`

启动日志默认写入 `logs/dev/`。

### 4. 分别启动后端和前端

只启动后端：

```bash
./start-backend.sh
```

只启动前端：

```bash
./start-frontend.sh
```

也可以通过统一脚本指定模式：

```bash
./start.sh backend
./start.sh frontend
```

### 5. 手动安装和启动

后端：

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn src.main:app --host 127.0.0.1 --port 7860
```

前端：

```bash
cd frontend
npm install
BACKEND_API_BASE_URL=http://127.0.0.1:7860 npm run dev -- --hostname 127.0.0.1 --port 3000
```

## Docker 部署

准备 `config.yaml` 后可使用 Docker Compose 启动：

```bash
docker compose up --build
```

服务端口：

- 后端：`http://localhost:7860`
- 前端：`http://localhost:3000`

如需调整前端允许来源、认证密钥，可通过环境变量传入：

```bash
FRONTEND_ORIGINS=http://localhost:3000 \
HYDROAUTH_SECRET=change-this-auth-secret \
docker compose up --build
```

## 默认账号

系统初始化时会创建以下内置账号，便于完成首次登录和权限验证：

| 角色 | 用户名 | 密码 |
| --- | --- | --- |
| 管理员 | `admin` | `admin123` |
| 运营经理 | `manager` | `manager123` |
| 值班操作员 | `operator` | `operator123` |
| 只读观察员 | `viewer` | `viewer123` |
| 审计员 | `auditor` | `auditor123` |

部署到共享或生产环境前，请修改默认密码并配置独立的认证密钥。

## 常用脚本与环境变量

启动脚本支持以下模式：

```bash
./start.sh all
./start.sh backend
./start.sh frontend
./start.sh --help
```

常用环境变量：

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `PYTHON_BIN` | 创建虚拟环境使用的 Python 命令 | `python3` |
| `BACKEND_HOST` | 后端监听地址 | `127.0.0.1` |
| `BACKEND_PORT` | 后端端口 | `7860` |
| `FRONTEND_HOST` | 前端监听地址 | `127.0.0.1` |
| `FRONTEND_PORT` | 前端端口 | `3000` |
| `FRONTEND_ORIGINS` | FastAPI CORS 允许来源 | `http://127.0.0.1:3000,http://localhost:3000` |
| `BACKEND_API_BASE_URL` | 前端服务端路由访问后端的地址 | `http://127.0.0.1:7860` |
| `INSTALL_BACKEND_DEPS` | 后端依赖安装策略：`auto`、`always`、`never` | `auto` |
| `INSTALL_FRONTEND_DEPS` | 前端依赖安装策略：`auto`、`always`、`never` | `auto` |
| `LOG_DIR` | 启动日志目录 | `logs/dev` |

示例：

```bash
BACKEND_PORT=8786 FRONTEND_PORT=3300 LOG_DIR=logs/local ./start.sh
```

## 质量检查

前端检查：

```bash
cd frontend
npm run typecheck
npm run lint
npm run build
```

后端测试：

```bash
. .venv/bin/activate
python -m unittest discover -s tests
```

如需检查单个测试文件：

```bash
python -m unittest tests.test_zone_planning
```

## 性能分析与优化计划

- [2026-11-18 完整更新记录](docs/update-record-2026-11-18.md)：汇总页面、接口、安全、构建代理、验证边界及部署回退步骤。
- [登录接口 404 与 HTML 错误修复](docs/fix-login-route-404.md)：记录路由故障现场、错误提示、启动检查及实际登录验证。
- [Open-Meteo 天气代理](docs/fix-weather-proxy.md)：配置顶层 `proxy`，仅用于天气预报目标主机。
- [Embedding 独立地址](docs/embedding-endpoint-configuration.md)：独立 URL、Key、模型列表与回退规则。
- [总览、调度与大屏性能分析](docs/performance-analysis.md)：记录页面切换耗时、接口实测、源码调用链和诊断边界。
- [总览、调度与大屏性能优化计划](docs/performance-optimization-plan.md)：列出分阶段优化、接口调整、安全约束和验收目标。
- [总览、调度与大屏优化实施记录](docs/performance-optimization-results.md)：记录已实施变更、隔离生产构建实测、测试结果和验证限制；第 5 节包含数据大屏优化。

## 安全说明

- 不要将真实 API Key、数据库密码或认证密钥提交到仓库。
- 共享环境中必须修改默认账号密码。
- 灌溉执行应始终经过计划、审批和执行记录链路。
- 接入真实执行器前，应完成设备状态检测、权限隔离、异常回滚和人工急停机制。
