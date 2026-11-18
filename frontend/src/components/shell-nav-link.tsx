'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { cn } from '@/lib/utils'

export function ShellNavLink({ href, children }: { href: string; children: React.ReactNode }) {
  const active = usePathname() === href
  return (
    <Link href={href} aria-current={active ? 'page' : undefined} className={cn('shell-nav-link', active && 'is-active')}>
      {children}
    </Link>
  )
}
