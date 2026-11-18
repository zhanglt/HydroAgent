# 登录接口 404 与页面显示 HTML 修复

日期：2026-11-18。

## 现场证据

登录页点击提交后，错误区域出现完整的 Next.js 404 HTML 和脚本数据。现场实际请求结果为：

| 请求 | 结果 |
| --- | --- |
| 前端 3000：`POST /api/auth/login` | 404，`text/html`，正文为 Next.js not-found 页面 |
| 后端 7860：同一账号直连登录 | 200，JSON 包含 token 和 user |
| 前端其他 API 路由 | `/api/auth/me`、logout、weather、visualization 同样返回 HTML 404 |

源码中登录路由文件存在，开发服务路由清单也有记录。原服务停止后，用同一份代码、同一开发输出目录在隔离端口重新启动 Next.js，登录路由立即被识别；当时后端未启动，请求由路由处理器抛出连接失败，已不再是 not-found 页面。没有删除源码、数据库、聊天历史或 `.next` 输出。

已确认这是当时运行中的前端 API 路由不可用，而非该账号密码校验失败。现有证据不能进一步证明是某个特定缓存文件损坏；重启后恢复不能等同于已经找到 Next.js 内部失效的确切原因。

## 代码修复

- `frontend/src/components/login-form.tsx` 不再把 `response.text()` 原样展示；通过 `frontend/src/lib/login-error.ts` 提取简短 JSON 错误，区分密码错误、路由不可用、限流和服务错误。HTML、损坏 JSON、异常详情及网络异常均采用安全提示。成功响应也检查 JSON 和用户信息，避免把 HTML 200 当成登录成功。错误区域增加 `role=alert`。
- `frontend/src/app/api/auth/login/route.ts` 在后端不可达时返回 JSON 503；上游 HTML、损坏成功 JSON、缺少 token/user 时返回 JSON 502，不透传 HTML，也不写 Cookie。合法后端鉴权失败保留状态码并返回简短 JSON 错误；合法成功仍只向浏览器返回 user，token 存入 HttpOnly Cookie。
- `start.sh` 在既有首页就绪检查之后增加 `OPTIONS /api/auth/login` 检查，利用 Next.js 的自动 OPTIONS 响应确认登录路由存在。该检查不提交账号密码，也不验证后端可达性或实际登录；前端独立启动仍可用于调试后端断开场景。

## 验证

使用隔离端口 3301 和临时数据库后端，未启动真实灌溉调度器或执行设备动作。

- 实际代理登录：正确密码返回 JSON 200，仅包含 user，并写 HttpOnly Cookie；错误密码返回 JSON 401；OPTIONS 返回 204，Allow 包含 POST。
- 实际后端断开：登录代理返回 JSON 503，提示检查后端是否启动。
- 用受控上游模拟 HTML 404、损坏 JSON 200、缺少 token 的 JSON 200：代理均返回 JSON 502，均未写 Cookie。
- headless Chrome 操作实际登录表单：分别拦截为 HTML 404、JSON 401、连接失败、HTML 200，均显示对应简短提示，无原始 HTML 或脚本泄漏。随后通过真实认证路由成功登录，跳转 `/`，Cookie 为 HttpOnly，无浏览器 JS 异常。该项验证登录和导航，不作为总览业务数据全部加载完成的证明。
- `npm run test:login`：5 项错误解析回归全部通过，覆盖 HTML、JSON 详情、损坏 JSON、验证错误数组、过长/带标签详情及限流。
- `npm run lint`、`npm run typecheck`、`npm run build`、`bash -n start.sh` 和 `git diff --check` 通过。

复现检查命令（服务启动后）：

```bash
curl -i -X OPTIONS http://127.0.0.1:3000/api/auth/login
cd frontend
npm run test:login
```

OPTIONS 应返回 204，不能用首页 200 代替 API 路由检查。实际密码验证应在浏览器操作，避免将会话 token 打印进终端或文档。

## 生效与排查

按正常流程重新启动开发服务，例如 `./start.sh`；若使用生产方式，重新构建并启动前端。若再次出现多个 API 同时返回 Next.js HTML 404，先保留日志并检查前端实例、端口和部署版本，再重启对应前端进程。检查 `BACKEND_API_BASE_URL` 指向后端而非前端自身。不要通过删除用户数据库、私有配置、聊天历史或更改管理员密码来处理路由 404。

隔离验证进程完成后已关闭。本记录描述代码与隔离验证；提交或推送代码不代表已重新部署或重启业务服务。
