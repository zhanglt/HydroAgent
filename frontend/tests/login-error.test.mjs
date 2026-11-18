import assert from 'node:assert/strict'
import test from 'node:test'
import { readFile } from 'node:fs/promises'
import ts from 'typescript'

const source = await readFile(new URL('../src/lib/login-error.ts', import.meta.url), 'utf8')
const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext } })
const { readLoginError } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`)

test('HTML 404 produces a short route recovery message', async () => {
  const response = new Response('<!DOCTYPE html><html>404<script>debug payload</script></html>', {
    status: 404, headers: { 'content-type': 'text/html' },
  })
  const message = await readLoginError(response)
  assert.match(message, /登录接口暂时不可用/)
  assert.doesNotMatch(message, /html|script|debug/)
})

test('JSON authentication errors preserve the backend detail', async () => {
  const response = Response.json({ detail: '用户名或密码错误' }, { status: 401 })
  assert.equal(await readLoginError(response), '用户名或密码错误')
})

test('malformed JSON and validation arrays use the safe fallback', async () => {
  const response = new Response('{broken', { status: 502, headers: { 'content-type': 'application/json' } })
  assert.match(await readLoginError(response), /登录服务暂时不可用/)
  assert.match(await readLoginError(Response.json({ detail: [{ msg: 'required' }] }, { status: 422 })), /登录失败/)
})

test('HTML embedded in JSON details and oversized details are not displayed', async () => {
  for (const detail of ['<html>Internal debug data</html>', 'x'.repeat(201)]) {
    assert.equal(await readLoginError(Response.json({ detail }, { status: 500 })), '登录服务暂时不可用，请稍后重试')
  }
})

test('rate limits remain distinct from password failures', async () => {
  assert.match(await readLoginError(new Response('', { status: 429 })), /过于频繁/)
  assert.match(await readLoginError(new Response('', { status: 401 })), /用户名或密码错误/)
})
