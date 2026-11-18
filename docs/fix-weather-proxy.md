# Open-Meteo 天气代理修复

日期：2026-11-18。

原日志中的 `Read timed out (read timeout=10)` 表示 Open-Meteo 天气请求没有及时返回，不是传感器或聊天模型错误。现场同类请求直连失败，经 `http://10.0.0.8:30000` 代理返回 200。

按用户要求，在私有 `config.yaml` 顶层增加：

```yaml
proxy: http://10.0.0.8:30000
```

`src/config/config.py` 将字段读取为 `config.PROXY`。`src/data/data_processing.py` 按 URL 的实际 hostname 检查，当请求目标是 `api.open-meteo.com` 时向 Requests 传入对应的 HTTP/HTTPS 代理。不是全局环境代理，不影响聊天、向量请求、其他自定义天气主机或地理编码服务。字段缺失或为空时保持 Requests 的默认网络行为；此时已有的系统代理环境变量仍可按 Requests 自身规则生效。

本地私有配置已设置该地址，其他配置值保留。使用应用实际 `get_weather_summary('北京')` 查询成功：`status=ok`、`source=open-meteo`、4 天预报，本次请求约 1.13 秒。该数据为单次现场验证，不保证后续代理和天气上游始终可达。

天气预报入口共用 `DataProcessingModule`，包括服务汇总和天气工具；旧缓存、失败状态及安全约束保留。失败仍标记为 unavailable/stale，不能把网络失败当成晴天或无雨来启动灌溉。

天气相关回归集合运行 68 项，全部通过，包含新代理配置加载、目标主机代理传参、其他主机/地理编码不使用该字段、空配置及既有计划安全测试。未启动真实灌溉。

```bash
PYTHONPATH=tests .venv/bin/python -m unittest \
  test_weather_api test_config test_console_performance \
  test_zone_planning test_api_plans test_data_processing -v
```

上面的 68 项为本次第一次运行该集合的结果；后续新增其他配置测试会使相同命令的项数增加。

生效需按正常流程重启后端，使配置重新加载。没有为验证而重启用户的现有服务；`config.yaml` 受 Git 忽略，配置模板与 README 已补充字段说明。
