import { Suspense } from 'react'
import ConsoleLoading from './loading'
import { DashboardConsole } from '@/components/dashboard-console'
import { requirePermission } from '@/lib/auth'
import { getDashboardData, getSettingsData } from '@/lib/server-data'

export default async function DashboardPage() {
  await requirePermission('dashboard:view')
  return <Suspense fallback={<ConsoleLoading />}><DashboardContent /></Suspense>
}

async function DashboardContent() {
  const [dashboard, settings] = await Promise.all([
    getDashboardData(false),
    getSettingsData().catch(() => null),
  ])

  return (
    <DashboardConsole initialDashboard={dashboard} initialSettings={settings} />
  )
}
