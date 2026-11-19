# 多模型服务配置

配置格式见根目录 `config.template.yaml`。聊天与向量服务独立选择；无需修改灌溉计划、审批或执行流程。

## 选择与协议

`llm_model` 支持 `openai`、`minimax`，`embedding_model` 支持 `openai`、`ollama` 和兼容名称 `ollam`。每个分组可保留多个服务商配置，运行时各选一个。

未写 `provider` 时，按 YAML 顺序选择首个模型名称非空的分组。聊天使用 `model_name`，向量使用 `embedding_model_name`。没有非空模型时默认 OpenAI。空白的 MiniMax 占位分组不会覆盖已配置的 OpenAI。可显式选择：

```yaml
llm_model:
  provider: minimax
  openai:
    openai_api_key: ""
    openai_base_url: https://api.openai.com/v1
    openai_wire_api: responses
    model_name: gpt-6.1-sol
  minimax:
    minimax_api_key: ""
    minimax_base_url: https://api.minimax.io/v1
    model_name: MiniMax-M2.5
embedding_model:
  provider: ollam
  ollam:
    embedding_base_url: http://127.0.0.1:11434
    embedding_model_name: bge-m3:latest
```

模型名称须以实际账号或本地安装的模型为准。OpenAI 及兼容服务支持 `auto`、`responses`、`chat_completions`；MiniMax 通过其 OpenAI 兼容接口使用 Chat Completions，保留工具调用与推理内容，默认地址 `https://api.minimax.io/v1`。可选 `minimax_wire_api` 覆盖协议。Responses 继续使用流式请求和 `developer` 指令角色。

Ollama 使用原生 `POST /api/embed`，单批最多 32 条文本；文档入库与查询共用此路径。地址填写服务根 URL，不加 `/api/embed` 或 `/v1`。本地服务无需 API Key；若网关需要认证，可设置 `embedding_api_key`，不会回退或发送聊天 Key。关闭自动截断，过长输入由服务返回错误，避免悄悄丢失文本。

使用 OpenAI 兼容向量服务时：

```yaml
embedding_model:
  provider: openai
  openai:
    embedding_base_url: https://vectors.example/v1
    embedding_api_key: ""
    embedding_model_name: text-embedding-3-small
```

此时地址或密钥为空则分别回退到当前聊天地址或密钥；独立服务应配置自己的地址、模型和凭据。聊天协议不会改变 `/embeddings` 路径。

## 保存与兼容

旧版顶层字段继续可用；某一类的分组存在时，该类使用分组值，避免从旧顶层读取其他服务商的配置。`OPENAI_API_KEY`、`MINIMAX_API_KEY` 和 `EMBEDDING_API_KEY` 可覆盖相应密钥。配置加载器导出的环境值不会被下一次加载误认为外部覆盖值。

设置页显示当前 provider，模型、地址和协议编辑后写回活动分组，不覆盖其他分组。`GET /api/settings` 返回 `llm_provider`、`embedding_provider`；密钥只返回掩码状态。为兼容原前端，`openai_base_url`、`openai_api_key`、`openai_wire_api` 等设置 API 字段代表当前聊天服务商，选择 MiniMax 时映射到其 `minimax_*` 配置。

`PUT /api/settings` 可提交以下结构切换服务，并按原流程热重载 Agent（需要 `settings:manage` 权限）：

```json
{"llm_provider": "minimax", "embedding_provider": "ollama"}
```

也可同次提交模型、地址、密钥。候选配置完整校验后原子写盘，非法 provider 或协议不会写入。手动编辑 YAML 后需重启后端。

模型列表沿用 `GET /api/settings/openai-models?target=chat|embedding`。OpenAI 兼容服务使用 `/models`；Ollama 使用 `/api/tags` 并转换为相同的列表格式，不发送聊天密钥。MiniMax 服务是否提供模型枚举取决于上游部署，枚举不可用时可手动填写模型名。

`proxy` 保持原有语义，只用于 Open-Meteo 预报请求。聊天和向量服务不自动使用该字段。

## 向量库与验证

切换向量模型或向量空间后，需要重新生成已有文档向量。本次修改不会删除、迁移或自动重建现有 Chroma 数据。

离线回归命令：

```bash
PYTHONPATH=tests .venv/bin/python -m unittest \
  test_model_providers test_config test_embedding_endpoint test_responses_gateway \
  test_weather_api test_api_plans test_control_execution test_zone_planning -q
```

回归覆盖分组读取、显式切换、旧配置兼容、保存重载、密钥隔离与掩码、非法配置拒绝、Ollama 原生请求和模型列表。传输测试使用 HTTP mock，不代表实际供应商的连通性、账号权限或模型可用性。

2026-11-19 验证：上述主回归 65 项通过；补充外部密钥在重载与切换服务商时保持覆盖优先级的测试后，配置、provider、向量接口与 Responses 的最终针对性回归 33 项通过。前端 `npm run lint`、`npm run typecheck` 通过。

本地私有配置已能识别为 OpenAI Responses / `gpt-6.1-sol` 与 Ollama / `bge-m3:latest`。实际检查 `127.0.0.1:11434/api/tags` 连接失败，因此未执行真实向量生成；OpenAI、MiniMax 上游本轮未发起真实模型调用。需先使 Ollama 服务可达并安装模型，再验证真实入库或查询。
