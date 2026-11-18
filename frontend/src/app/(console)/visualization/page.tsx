import { VisualizationConsole } from '@/components/visualization-console'
import { requirePermission } from '@/lib/auth'

export default async function VisualizationPage() {
  const user = await requirePermission('dashboard:view')
  return <VisualizationConsole canReadSummary={user.permissions.includes('assets:view')} canReadModels={user.permissions.includes('operations:view')} />
}
