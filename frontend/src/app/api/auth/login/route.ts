import { NextRequest, NextResponse } from 'next/server'
import { AUTH_COOKIE_NAME } from '@/lib/auth'
import { fetchBackend } from '@/lib/backend'
import { readLoginError } from '@/lib/login-error'

function shouldUseSecureCookie(request: NextRequest) {
  const override = process.env.AUTH_COOKIE_SECURE
  if (override) return override === 'true'
  const forwardedProtocol = request.headers.get('x-forwarded-proto')
  return forwardedProtocol === 'https' || request.nextUrl.protocol === 'https:'
}

export async function POST(request: NextRequest) {
  let backendResponse: Response
  try {
    backendResponse = await fetchBackend('/api/auth/login', {
      method: 'POST',
      body: await request.text(),
    })
  } catch {
    return NextResponse.json({ detail: '无法连接登录服务，请检查后端服务是否启动' }, { status: 503 })
  }
  if (!backendResponse.headers.get('content-type')?.includes('application/json')) {
    return NextResponse.json({ detail: '登录服务返回了异常响应，请检查后端地址' }, { status: 502 })
  }
  if (!backendResponse.ok) {
    return NextResponse.json({ detail: await readLoginError(backendResponse) }, { status: backendResponse.status })
  }
  let payload: { token: string; user: Record<string, unknown> }
  try {
    payload = await backendResponse.json()
    if (typeof payload?.token !== 'string' || !payload.token || !payload.user || typeof payload.user !== 'object') {
      throw new Error('Invalid login payload')
    }
  } catch {
    return NextResponse.json({ detail: '登录服务返回了无效数据，请稍后重试' }, { status: 502 })
  }

  const response = NextResponse.json({ user: payload.user })
  response.cookies.set(AUTH_COOKIE_NAME, payload.token, {
    httpOnly: true,
    sameSite: 'lax',
    secure: shouldUseSecureCookie(request),
    path: '/',
    maxAge: 60 * 60 * 8,
  })
  return response
}
