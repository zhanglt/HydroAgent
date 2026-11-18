export default function ConsoleLoading() {
  return (
    <div role="status" aria-live="polite" className="surface-panel min-h-48">
      <p className="text-sm text-slate-500">正在加载页面数据…</p>
      <div aria-hidden="true" className="mt-4 h-24 animate-pulse rounded-lg bg-slate-100" />
    </div>
  )
}
