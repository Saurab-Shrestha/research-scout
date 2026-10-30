import { useQuery } from '@tanstack/react-query'
import { Compass, GraduationCap, KanbanSquare, LayoutDashboard, ListFilter, Menu, PenLine, UserRound } from 'lucide-react'
import { useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { api, CLOSED } from '@/lib/api'
import { daysUntil } from '@/lib/format'
import { cn } from '@/lib/utils'
import { ThemeToggle } from './theme'

const NAV = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/opportunities', label: 'Opportunities', icon: ListFilter },
  { to: '/tracker', label: 'Tracker', icon: KanbanSquare, badge: 'due' as const },
  { to: '/drafts', label: 'Draft studio', icon: PenLine },
  { to: '/discover', label: 'Discover', icon: Compass },
  { to: '/profile', label: 'Profile', icon: UserRound },
]

function useDueCount() {
  const { data } = useQuery({ queryKey: ['applications'], queryFn: api.applications })
  return (data ?? []).filter((a) => !CLOSED.includes(a.status) && (daysUntil(a.next_action_at) ?? 99) <= 2).length
}

function Nav({ onNavigate }: { onNavigate?: () => void }) {
  const due = useDueCount()
  return (
    <nav aria-label="Main" className="flex flex-col gap-0.5">
      {NAV.map(({ to, label, icon: Icon, end, badge }) => (
        <NavLink key={to} to={to} end={end} onClick={onNavigate}
          className={({ isActive }) => cn(
            'group flex h-9 items-center gap-3 rounded-lg px-3 text-sm font-medium transition-colors duration-150',
            'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring',
            isActive ? 'bg-sidebar-accent text-sidebar-accent-foreground' : 'text-sidebar-foreground/75 hover:bg-sidebar-accent/60 hover:text-sidebar-foreground',
          )}>
          <Icon aria-hidden className="size-4 shrink-0" />
          <span className="flex-1">{label}</span>
          {badge === 'due' && due > 0 && (
            <span className="rounded-full bg-warning px-1.5 text-[11px] font-semibold leading-5 text-warning-foreground tabular" aria-label={`${due} actions due soon`}>{due}</span>
          )}
        </NavLink>
      ))}
    </nav>
  )
}

function Brand() {
  return (
    <div className="flex items-center gap-2.5 px-3">
      <div className="grid size-8 place-items-center rounded-lg bg-primary text-primary-foreground"><GraduationCap aria-hidden className="size-4.5" /></div>
      <div className="leading-tight">
        <p className="font-heading text-lg font-semibold">Research Scout</p>
        <p className="text-[11px] text-muted-foreground">Funded grad positions</p>
      </div>
    </div>
  )
}

export function Layout() {
  const [open, setOpen] = useState(false)
  const { pathname } = useLocation()
  const current = NAV.find((n) => (n.end ? pathname === n.to : pathname.startsWith(n.to)))
  return (
    <div className="min-h-dvh bg-background">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-primary focus:px-3 focus:py-2 focus:text-primary-foreground">Skip to content</a>

      <aside className="fixed inset-y-0 left-0 z-20 hidden w-60 flex-col gap-6 border-r bg-sidebar py-5 lg:flex">
        <Brand />
        <div className="px-3"><Nav /></div>
        <div className="mt-auto flex items-center justify-between px-5 text-xs text-muted-foreground">
          <span>USA · Canada</span>
          <ThemeToggle />
        </div>
      </aside>

      <header className="sticky top-0 z-20 flex h-14 items-center gap-2 border-b bg-background/90 px-4 backdrop-blur lg:hidden">
        <Button variant="ghost" size="icon" aria-label="Open menu" onClick={() => setOpen(true)}><Menu className="size-5" /></Button>
        <span className="font-heading text-lg font-semibold">{current?.label ?? 'Research Scout'}</span>
        <div className="ml-auto"><ThemeToggle /></div>
      </header>
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent side="left" className="w-72 bg-sidebar p-0">
          <SheetHeader className="pt-5"><SheetTitle className="sr-only">Navigation</SheetTitle><Brand /></SheetHeader>
          <div className="px-3"><Nav onNavigate={() => setOpen(false)} /></div>
        </SheetContent>
      </Sheet>

      <main id="main" className="lg:pl-60">
        <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
