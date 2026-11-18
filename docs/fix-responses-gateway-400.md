# 第三方 Responses 网关 400 修复

日期：2026-11-18。涉及 `src/llm/langchain_agent.py`、配置管理、设置 API 与前端设置页。

## 现象与实际原因

`POST /api/chat` 返回 HTTP 200，随后第三方网关的 `POST /openai/responses` 请求返回 400。HTTP 200 只代表 SSE 通道已建立；模型错误在后续流事件中返回，不能据此判断聊天成功。本文使用占位域名，实际服务地址仅保留在本地私有配置中。

现场配置模型为 `gpt-6.1-sol`。LangChain 在该模型绑定工具时自动选择 Responses API，但请求中仍有 `role: system` 的输入项。使用应用实际模型类和一个无副作用的测试工具复现后，读取到上游响应正文：

```json
{"detail":"System messages are not allowed"}
```

仅将同组请求的系统指令出站角色改为 `developer` 后，网关返回 200 并输出 `OK`。因此本次修复针对已复现的角色约束；不是把接口改成 Chat Completions，也没有移除灌溉安全指令。基础地址沿用用户给出的地址，不追加 `/v1` 或重复 `/responses`。

## 配置与修复

用户的 Codex 配置：

```toml
base_url = "https://gateway.example/openai"
wire_api = "responses"
```

本项目 `config.yaml` 对应：

```yaml
openai_base_url: https://gateway.example/openai
openai_wire_api: responses
model_name: gpt-6.1-sol
```

本地私有 `config.yaml` 已设置 `openai_wire_api: responses`，其余配置值已比较确认保留；该文件受 Git 忽略，密钥不纳入补丁。

新增 YAML 字段 `openai_wire_api`，默认 `auto`，可选 `responses`、`chat_completions`。配置读取、保存、设置 API 请求/响应、设置页与 Agent 热重载全部接入。非法协议在 API 返回 422，直接配置保存则在写盘前拒绝。字段沿用模型配置由 YAML 托管的规则，不增加环境变量覆盖。

Agent 初始化将该配置映射为 LangChain 的 `use_responses_api`；主模型与参数解析子模型共用同一实例。Responses 请求在最终 payload 构造处将全部 `system` 输入角色转成 `developer`，包括安全指令和运行上下文，保留内容及本地消息对象。流式设置保持开启。Chat Completions 的系统角色与 DeepSeek `reasoning_content` 回传逻辑保留；工具调用 ID 和结果关联保持一致。Embeddings 接口不受聊天协议字段影响。

## 验证

### 离线回归

```bash
PYTHONPATH=tests .venv/bin/python -m unittest \
  test_responses_gateway test_config test_tool_argument_parser test_chat_persistence -v
cd frontend
npm run lint
npm run typecheck
npm run build
```

后端相关集合 21 项通过，无跳过；前端 lint、类型检查与生产构建通过。新增覆盖 Responses 多条系统指令映射及原对象保留、自动选择分支、Chat Completions 推理字段兼容、工具结果 ID、结构化参数解析、初始化协议传递、配置持久化与非法值拒绝，以及设置 API 保存和热重载。

### 真实网关、隔离应用验证

- 使用现有本地凭据、实际配置模型和网关；网络经当前环境代理访问，不打印认证令牌。
- 临时 SQLite 数据库、临时会话/checkpointer，实际挂载认证与 `/api/chat` 路由，使用实际 `HydroDeepAgent.chat_stream`、LangChain Agent 和 SDK。将天气、农场上下文及技能选择换为隔离测试输入，仅注册无设备副作用的 `read_status` 工具，不启动调度器或真实 MCP 执行工具。
- 同一临时会话连续两次 `POST /api/chat` 均为 200，分别返回 `text` 和 `done`，回答均为 `OK`，无 `error` 事件；两次上游 `/responses` 请求均返回 200。
- 另用同一模型强制生成一次只读测试工具调用，再将对应 `ToolMessage` 回传模型；两次请求均成功，验证工具调用与结果的往返格式。测试没有调用真实执行器或生成、批准、执行灌溉计划。

该结果验证网关协议、SSE 文本、临时多轮历史与测试工具格式。未遍历所有真实 MCP 工具或业务会话，不代表每个网关模型都支持全部工具 schema。旧会话若另有格式问题，应单独检查，不能在缺少证据时清空聊天记录。

## 生效方式

更新后重新启动后端使新的请求转换代码生效；前端重新构建后，设置页“常规”中可选择“聊天 API 协议”。代码加载后通过设置 API 保存协议会热重载 Agent，既有会话无需删除。验证时同时检查上游状态和 SSE 中的 `text/error/done`，不要只检查聊天入口 HTTP 200。
