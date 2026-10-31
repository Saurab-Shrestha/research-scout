import { useQuery } from '@tanstack/react-query'
import { Bookmark, CalendarDays, FilePenLine, GraduationCap, Kanban, LayoutDashboard, Menu, Microscope, Search, Settings, UserRound, type LucideIcon } from 'lucide-react'
import { useState } from 'react'
import { Link, NavLink, Outlet } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { api, CLOSED, type Degree } from '@/lib/api'
import { countryList, daysUntil, DEGREE } from '@/lib/format'
import { cn } from '@/lib/utils'
import { ThemeToggle } from './theme'

type Item = { to: string; label: string; icon: LucideIcon; end?: boolean; badge?: 'due' | 'saved' }
const NAV: { group: string; items: Item[] }[] = [
  { group: 'Workspace', items: [
    { to: '/', label: 'Overview', icon: LayoutDashboard, end: true },
    { to: '/opportunities', label: 'Discover', icon: Search },
    { to: '/shortlist', label: 'Shortlist', icon: Bookmark, badge: 'saved' },
    { to: '/researchers', label: 'Researchers', icon: Microscope },
  ] },
  { group: 'Applications', items: [
    { to: '/tracker', label: 'Application Tracker', icon: Kanban, badge: 'due' },
    { to: '/drafts', label: 'Writing Studio', icon: FilePenLine },
  ] },
  { group: 'Personal', items: [
    { to: '/profile', label: 'Academic Profile', icon: UserRound },
    { to: '/settings', label: 'Settings', icon: Settings },
  ] },
]

function useCounts() {
  const { data } = useQuery({ queryKey: ['applications'], queryFn: api.applications })
  const apps = data ?? []
  return {
    due: apps.filter((a) => !CLOSED.includes(a.status) && (daysUntil(a.next_action_at) ?? 99) <= 2).length,
    saved: apps.filter((a) => a.status === 'shortlisted').length,
  }
}

function Wordmark() {
  return (
    <Link to="/" aria-label="Research Scout, overview" className="flex items-center gap-2.5 rounded-md focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ring">
      <GraduationCap aria-hidden className="size-8 text-navy" strokeWidth={1.75} />
      <span className="leading-none">
        <span className="block font-heading text-[1.3rem] font-semibold tracking-[-0.01em] text-navy">Research Scout</span>
        <span className="mt-1 block text-xs text-muted-foreground">Find. Verify. Apply.</span>
      </span>
    </Link>
  )
}

function Nav({ onNavigate }: { onNavigate?: () => void }) {
  const { due, saved } = useCounts()
  return (
    <nav aria-label="Main" className="space-y-5">
      {NAV.map(({ group, items }) => (
        <div key={group}>
          <p className="mb-1.5 px-3 text-[0.6875rem] font-medium tracking-[0.06em] text-meta uppercase">{group}</p>
          <ul className="space-y-0.5">
            {items.map(({ to, label, icon: Icon, end, badge }) => (
              <li key={to}>
                <NavLink to={to} end={end} onClick={onNavigate}
                  className={({ isActive }) => cn(
                    'flex h-10 items-center gap-3 rounded-lg px-3 text-[0.9375rem] font-medium transition-colors duration-(--dur-micro)',
                    'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring',
                    isActive ? 'bg-signal text-signal-ink' : 'text-ink-soft hover:bg-well hover:text-foreground',
                  )}>
                  <Icon aria-hidden className="size-[18px] shrink-0" />
                  <span className="flex-1">{label}</span>
                  {badge === 'saved' && saved > 0 && <span className="num text-xs opacity-75" aria-label={`${saved} saved`}>{saved}</span>}
                  {badge === 'due' && due > 0 && <span className="num rounded-full bg-warning-soft px-1.5 text-xs text-warning" aria-label={`${due} actions due soon`}>{due}</span>}
                </NavLink>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  )
}

/** The intake the whole search is aimed at, read from the profile. */
function IntakeSummary() {
  const { data } = useQuery({ queryKey: ['profile'], queryFn: api.profile, retry: false })
  if (!data?.intended_start_term) return null
  const degrees = (Object.keys(DEGREE) as Degree[]).filter((d) => data.target_degrees.includes(d)).map((d) => DEGREE[d])
  return (
    <Link to="/profile" className="flex gap-3 rounded-xl bg-well px-4 py-3.5 transition-colors hover:bg-well-2 focus-visible:outline-2 focus-visible:outline-ring">
      <CalendarDays aria-hidden className="mt-0.5 size-[18px] shrink-0 text-navy" />
      <span>
        <span className="block font-semibold text-foreground">{data.intended_start_term}</span>
        <span className="block text-xs text-muted-foreground">{degrees.join(' · ')}<br />{countryList(data.target_countries)}</span>
      </span>
    </Link>
  )
}

function UserRow() {
  const { data } = useQuery({ queryKey: ['profile'], queryFn: api.profile, retry: false })
  const name = data?.name || 'Your profile'
  return (
    <div className="flex items-center gap-2.5 border-t border-border pt-4">
      <Link to="/profile" className="flex min-w-0 flex-1 items-center gap-2.5 rounded-md focus-visible:outline-2 focus-visible:outline-ring">
        <span aria-hidden className="grid size-8 shrink-0 place-items-center rounded-full bg-navy text-sm font-semibold text-navy-ink">{name[0]?.toUpperCase()}</span>
        <span className="truncate text-sm font-medium text-foreground">{name}</span>
      </Link>
      <ThemeToggle />
    </div>
  )
}

function SidebarBody({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <div className="flex h-full flex-col gap-8 px-4 py-6">
      <div className="px-2"><Wordmark /></div>
      <Nav onNavigate={onNavigate} />
      <div className="mt-auto space-y-4">
        <IntakeSummary />
        <UserRow />
      </div>
    </div>
  )
}

export function Layout() {
  const [open, setOpen] = useState(false)
  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[240px_1fr]">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-3 focus:z-[600] focus:rounded-md focus:bg-navy focus:px-3 focus:py-2 focus:text-navy-ink">Skip to content</a>

      <aside className="hidden border-r border-border bg-sidebar lg:block">
        <div className="sticky top-0 h-dvh overflow-y-auto"><SidebarBody /></div>
      </aside>

      <header className="sticky top-0 z-[300] flex h-14 items-center justify-between border-b border-border bg-sheet px-4 lg:hidden">
        <Wordmark />
        <Button type="button" variant="ghost" size="icon" aria-label="Open menu" onClick={() => setOpen(true)}><Menu /></Button>
      </header>

      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent side="left" className="w-72 bg-sidebar p-0">
          <SheetHeader className="sr-only"><SheetTitle>Menu</SheetTitle></SheetHeader>
          <SidebarBody onNavigate={() => setOpen(false)} />
        </SheetContent>
      </Sheet>

      <main id="main" className="mx-auto w-full min-w-0 max-w-[1360px] px-4 py-7 sm:px-8 lg:px-10 lg:py-9">
        <Outlet />
      </main>
    </div>
  )
}
