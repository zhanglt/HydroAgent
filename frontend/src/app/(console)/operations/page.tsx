import { OperationsConsole } from '@/components/operations-console'
import { requirePermission } from '@/lib/auth'

export default async function OperationsPage() {
  const user = await requirePermission('operations:view')
  return <OperationsConsole currentUser={user} />
}
