export async function readLoginError(response: Response): Promise<string> {
  const fallback = response.status === 401 ? '用户名或密码错误' :
    response.status === 404 ? '登录接口暂时不可用，请重启前端服务后重试' :
    response.status === 429 ? '登录请求过于频繁，请稍后重试' :
    response.status >= 500 ? '登录服务暂时不可用，请稍后重试' : '登录失败，请检查账号状态后重试'

  if (!response.headers.get('content-type')?.includes('application/json')) return fallback
  try {
    const payload = await response.json()
    const detail = payload?.detail
    if (typeof detail === 'string' && detail.trim() && detail.length <= 200 && !/[<>]/.test(detail)) {
      return detail
    }
  } catch {
    return fallback
  }
  return fallback
}
