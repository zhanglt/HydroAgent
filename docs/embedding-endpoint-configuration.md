# Embedding 独立服务地址

日期：2026-11-18。

2026-11-19 更新：以下记录描述旧版平铺配置，仍然兼容。新版支持 `embedding_model.openai` 与 `embedding_model.ollama`（兼容 `ollam`），配置及切换规则见[多模型服务配置](model-provider-configuration.md)。

## 配置

`config.yaml` 新增顶层 `embedding_base_url`，与 `embedding_model_name`、已有的 `embedding_api_key` 配套使用：

```yaml
openai_base_url: https://your-chat-provider/openai
openai_wire_api: responses
embedding_model_name: text-embedding-3-small
embedding_base_url: https://your-embedding-provider/v1
# embedding_api_key: your-embedding-provider-key
proxy: http://10.0.0.8:30000
```

示例地址需替换为服务商给出的基础 URL，不要在末尾手动追加 `/embeddings`。聊天协议和向量接口是独立的：`openai_wire_api: responses` 不会把向量请求发往 Responses API。

用户尚未提供独立服务的实际地址，因此本地私有配置先增加 `embedding_base_url: ""`，不把示例地址写成运行地址。留空、缺失或空白字符串时，向量请求继续复用 `openai_base_url`；单独设置后，知识库入库和语义查询均使用该地址。已有 Embedding Key 未配置时仍回退到聊天 Key。

`proxy` 仅供 `api.open-meteo.com` 使用，不会自动为独立向量服务设置代理，见[天气代理记录](fix-weather-proxy.md)。

## 接入位置

- 配置管理读取、保存和返回 `embedding_base_url`，设置页“知识引擎”新增 Embeddings Endpoint。保存空字符串可恢复共用聊天地址；模型与地址继续由 YAML 托管。
- `KnowledgeBaseService._embed_texts()` 在每次初始化 SDK 时选择 `EMBEDDING_BASE_URL or OPENAI_BASE_URL`。入库与检索共用此入口，既有向量集合不被删除或迁移。
- 模型列表接口新增 `target=chat|embedding`，默认 chat。Embedding 选择器请求 `target=embedding`，使用独立向量地址与对应 Key；未单独配置时回退。此处使用已保存配置，修改地址后先保存再打开模型列表。
- 设置 API 将新字段写入 YAML，并按现有模型设置流程热重载 Agent。SDK 本身按调用创建，因此新的知识库请求使用更新后的地址。
- 与既有模型字段保持一致，同步到进程环境的 `EMBEDDING_BASE_URL` 为实际生效地址；配置来源仍为 YAML，不新增环境变量覆盖规则。

更换 Embedding 模型或向量空间时，已有向量需要按新模型重新生成才能正确比较；仅增加独立地址不会自动重新索引文档。

## 验证

```bash
PYTHONPATH=tests .venv/bin/python -m unittest \
  test_embedding_endpoint test_config test_responses_gateway \
  test_weather_api test_api_plans test_console_performance -v
cd frontend
npm run lint
npm run typecheck
npm run build
```

该后端集合共 52 项，全部通过，无跳过；前端 lint、类型检查和生产构建通过。新测试覆盖：独立地址与 Key 的选择、配置落盘、清空回退、聊天地址变化不覆盖独立地址、模型列表目标参数校验、设置 API 保存与热重载。

向量请求测试使用实际 OpenAI SDK 和 HTTPX MockTransport，确认入库/查询请求发往独立服务的 `/v1/embeddings`，使用 Embedding 模型及 Key。没有调用用户尚未提供的新服务，也没有读取或重建真实向量库；因此新服务的连通性、模型存在性与认证需要提供真实地址后再验证。

通过 YAML 修改需重启后端使配置重新加载；代码加载后也可在设置页保存地址。私有 `config.yaml` 不纳入 Git，配置模板及 README 已更新。
