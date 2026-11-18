# 总览与调度页面性能分析

分析日期：2026-11-18。状态：优化前的历史诊断快照，以下调用链描述当时实现；源码链接指向当前文件。代码优化及实际验证结果见[优化实施记录](performance-optimization-results.md)，原始目标见[性能优化计划](performance-optimization-plan.md)。

## 1. 结论与环境

总览和调度的主要等待发生在服务端数据读取链路：传感器展示间接触发同步天气请求，页面又等待全部依赖返回后才构造内容。调度额外读取大量未用于展示的历史数据；总览还存在图表依赖和首屏动画成本。

诊断环境为本机 Next.js 开发服务 `http://127.0.0.1:3000`、FastAPI 服务 `http://127.0.0.1:7860`，当时运行的 Next.js 版本为 16.2.2。以下数据来自本次会话前两轮诊断的截图、HTTP 请求实测和 `logs/dev/frontend.log`，不代表生产构建表现。本次文档交付没有重新进行性能采样。

HTTP 探测使用正常登录后的请求，只访问页面和读取接口，没有调用生成计划、审批或执行接口。日志摘录直接保存在本文中，以免运行日志轮转后丢失证据。

## 2. 观测结果及边界

### 浏览器截图

| 页面 | LCP | INP | CLS | LCP 候选元素 |
| --- | --- | --- | --- | --- |
| 总览 `/` | 4.03 秒 | 64 毫秒 | 0 | 页面顶部说明文字 |
| 调度 `/operations` | 2.87 秒 | 24 毫秒 | 0 | 侧栏说明文字 `p.shell-sidebar-note` |

LCP 表示浏览器记录的最大内容绘制时间，INP 反映已记录交互的响应情况，CLS 反映布局偏移。两张截图显示内容出现偏晚，但已记录的交互响应和布局稳定性较好。

这些值不能直接等同于“点击导航到目标内容可见”的耗时，尤其不能仅凭客户端路由切换后的指标面板判断单次切换。LCP 候选是文字，也不证明文字本身渲染昂贵。精确拆分需要浏览器 Performance 轨迹、网络瀑布图和点击时间标记。

### HTTP 实测

| 诊断场景 | 请求 | 耗时 |
| --- | --- | --- |
| 总览诊断 | 总览页面 `/` | 1.521 秒 |
| 总览诊断 | `/api/dashboard` | 0.812 秒 |
| 总览诊断 | 后端 `/api/sensors/current` | 1.009 秒 |
| 总览诊断 | 后端认证、状态、计划、分区等接口，分别单独请求 | 约 35～50 毫秒/次 |
| 总览诊断 | 总览依赖的 7 个后端接口并发请求 | 各约 0.86～0.91 秒，整批约 0.915 秒 |
| 独立天气诊断 | Open-Meteo 外部请求，HTTP 200 | 1.334 秒 |
| 调度诊断 | `/operations`，两次请求 | 2.703 秒、1.836 秒 |
| 调度诊断 | `/api/history` | 0.858 秒 |
| 调度诊断 | `/api/dashboard` | 0.858 秒 |
| 调度诊断 | 历史数据的 7 个后端接口，分别单独请求 | 各约 35～38 毫秒 |

样本来自不同时间、不同缓存和后台负载状态，不应相加、直接比较为优化收益或作为稳定性能基线。HTTP 整体响应时间也不等于浏览器内容绘制时间。

### 历史服务日志

```text
GET / 200 in 12.5s (next.js: 1929µs, application-code: 12.5s)
GET /api/dashboard 200 in 11.3s (next.js: 29ms, application-code: 11.3s)
GET /operations 200 in 13.4s (next.js: 24ms, application-code: 13.4s)
GET /operations 200 in 10.5s (next.js: 2ms, application-code: 10.5s)
GET /operations 200 in 12.3s (next.js: 1951µs, application-code: 12.3s)
GET /operations 200 in 8.5s (next.js: 2ms, application-code: 8.4s)
GET /operations 200 in 2.7s (next.js: 1873µs, application-code: 2.7s)
GET /operations 200 in 1835ms (next.js: 1443µs, application-code: 1833ms)
```

这些长请求的时间主要记在应用代码中，Next.js 框架处理通常仅占几毫秒。开发编译不能解释这些特定请求的全部耗时；但其他路由首次进入时仍可能发生开发编译成本。

现有日志缺少每个依赖的开始、结束和缓存命中记录，无法证明每次十几秒的请求都由天气超时引起，也无法精确量化数据库、鉴权、聚合和序列化各自的占比。

## 3. 调用链与共同问题

### 服务端整页等待

```text
总览：权限校验
  -> 并行等待 getDashboardData() 和 getSettingsData()
  -> 构造 AppShell 和总览内容

调度：权限校验
  -> 并行等待 getHistoryData() 和 getDashboardData()
  -> 构造 AppShell 和调度内容

getDashboardData()：并行请求 7 个接口
  -> 系统状态、当前传感器、天气、灌溉状态、决策、分区、计划

当前传感器接口：逐分区 get_zone_status()
  -> collect_zone_evidence()
  -> 传感器 + 天气 + 设置 + 计划 + 执行器信息
```

依据：[总览入口](<../frontend/src/app/(console)/page.tsx>)、[调度入口](<../frontend/src/app/(console)/operations/page.tsx>)、[服务端取数](../frontend/src/lib/server-data.ts)、[传感器接口](../src/api.py)、[灌溉服务](../src/services/irrigation_service.py)。页面入口因共享布局调整已迁入 `(console)` 路由组，URL 保持不变。

### 传感器展示绑定外部天气

`get_current_sensors()` 只使用 `get_zone_status()` 返回的传感器摘要，但后者收集完整灌溉证据，其中包含 `_get_weather_summary()`。因此读取湿度、温度也可能等待外部天气。同样，天气接口通过完整分区状态取天气，也读取了其他证据。

### 同步网络调用阻塞异步路由

传感器和天气路由是 `async def`，但内部调用的天气模块使用同步 `requests.get(..., timeout=10)`，见[天气处理模块](../src/data/data_processing.py)。直接调用时，等待网络会阻塞当前 worker 的事件循环，其他请求也可能一起等待。

本次并发测试中，多个原本单独约 40 毫秒的接口一起变为约 0.9 秒，与这一代码路径相符。仍需通过慢天气故障注入和请求级追踪进一步隔离各项成本。`timeout=10` 是 Requests 网络超时配置，不是整个页面请求必定在 10 秒结束的保证。

### 缓存周期与轮询

`EVIDENCE_CACHE_TTL_SECONDS = 5` 同时控制传感器和天气缓存。总览与调度的总览数据轮询也是 5 秒，容易在下一轮刷新时再次遇到过期天气缓存；并非每轮都必然请求外网。缓存锁仅保护字典读写，没有合并同地点正在进行的天气请求。

### 页面反馈与缓存边界

[AppShell](../frontend/src/components/app-shell.tsx)放在各页面内部，当前没有 `loading.tsx` 或用于这些区域的分段加载边界。切换需要服务端响应时，旧内容可能停留直到新页面可用，用户缺少即时反馈。

[React Query](../frontend/src/components/query-provider.tsx)缓存位于客户端，而[后端请求封装](../frontend/src/lib/backend.ts)使用 `cache: 'no-store'`。客户端已有数据不能直接跳过服务端页面函数的等待。路由缓存和预取还会影响实际切换，须在浏览器测试中单独记录。

## 4. 页面差异

### 总览

[总览组件](../frontend/src/components/dashboard-console.tsx)直接引入 `echarts-for-react`，其默认入口加载完整 ECharts。诊断时 ECharts 与 zrender 的开发 JavaScript 产物共 23 个文件，磁盘未压缩大小约 6.29 MiB，不含 source map。该数字不是页面实际加载文件总量、压缩传输量或生产包大小。

页面容器以 `initial="hidden"` 开始，动画状态包含 `opacity: 0`，客户端接管后播放渐显和位移动画。该方式可能推迟标题与说明文字可见时间，具体占比尚无浏览器轨迹验证。

### 调度

[调度组件](../frontend/src/components/operations-console.tsx)没有直接引入 ECharts，也没有总览那样的整体入场动画，其优先优化对象是数据依赖。

调度同时等待 7 个总览接口和 7 个历史接口，权限校验另算。历史接口包括灌溉日志、决策、会话、普通计划、活跃计划、工具调用和审计；组件只从历史结果中提取活跃计划，普通计划作为备用来源。分区区域主要依赖分区和传感器摘要，但仍请求完整总览。

这些请求并行发出，耗时不是 14 个接口时间之和；多余请求仍增加鉴权、查询、序列化和调度成本，并扩大必须等待的依赖范围。当前每 5 秒刷新完整总览、每 10 秒刷新完整历史，使额外读取持续发生。

## 5. 判断与后续验证

| 结论 | 证据等级 | 尚待补齐 |
| --- | --- | --- |
| 两页存在秒级服务端等待 | 日志与 HTTP 实测确认 | 固定环境下的多样本分布 |
| 传感器查询会读取天气 | 源码确认 | 拆分前后的请求次数对照 |
| 异步路由中直接执行同步天气请求 | 源码确认，并发实测与影响相符 | 故障注入下事件循环响应对照 |
| 调度存在未使用的历史数据读取 | 源码确认 | 精简后的请求数、响应大小和耗时 |
| 图表和动画增加总览首屏成本 | 依赖及初始隐藏由源码确认 | 浏览器 CPU、网络及绘制占比 |
| 某次长请求完全由天气超时造成 | 尚未证实 | 请求级依赖计时与关联标识 |

优化时必须保留灌溉证据与审批约束。展示缓存不能代替计划安全校验，天气异常不能解释为无雨，缺失传感器值不能解释为正常或零湿度。实施顺序和验收方法见[性能优化计划](performance-optimization-plan.md)。
