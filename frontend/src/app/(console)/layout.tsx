import { AppShell } from '@/components/app-shell'

export default function ConsoleLayout({ children }: { children: React.ReactNode }) {
  return <AppShell currentPath="/">{children}</AppShell>
}
