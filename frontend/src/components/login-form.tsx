'use client'

import { FormEvent, useState, useTransition } from 'react'
import { useRouter } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { readLoginError } from '@/lib/login-error'

export function LoginForm() {
  const router = useRouter()
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('admin123')
  const [error, setError] = useState<string | null>(null)
  const [isPending, startTransition] = useTransition()

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    startTransition(async () => {
      setError(null)
      try {
        const response = await fetch('/api/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username, password }),
        })

        if (!response.ok) {
          setError(await readLoginError(response))
          return
        }
        if (!response.headers.get('content-type')?.includes('application/json')) {
          setError('登录服务返回了异常响应，请稍后重试')
          return
        }
        const payload = await response.json()
        if (!payload?.user || typeof payload.user !== 'object') {
          setError('登录服务返回了异常响应，请稍后重试')
          return
        }

        router.push('/')
        router.refresh()
      } catch {
        setError('无法连接登录服务，请检查网络后重试')
      }
    })
  }

  return (
    <form className="login-form" onSubmit={handleSubmit}>
      <label className="login-field">
        <span>用户名</span>
        <Input value={username} autoComplete="username" onChange={(event) => setUsername(event.target.value)} />
      </label>
      <label className="login-field">
        <span>密码</span>
        <Input type="password" value={password} autoComplete="current-password" onChange={(event) => setPassword(event.target.value)} />
      </label>
      {error ? <div className="login-error" role="alert">{error}</div> : null}
      <Button className="mt-1 h-10 w-full rounded-lg bg-gradient-to-r from-[#0052FF] to-[#4D7CFF] text-sm font-semibold text-white shadow-sm shadow-blue-500/20 hover:-translate-y-0.5 hover:shadow-lg hover:shadow-blue-500/30" type="submit" disabled={isPending}>
        {isPending ? 'Signing in...' : 'Enter Credentials'}
      </Button>
    </form>
  )
}
