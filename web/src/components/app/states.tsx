import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import type { LucideIcon } from 'lucide-react'

/** An empty region says what belongs here and the one action that fills it. */
export function EmptyState({ icon: Icon, title, children, action }: { icon?: LucideIcon; title: string; children?: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-start gap-3 rounded-xl border border-dashed border-input bg-sheet px-6 py-8">
      {Icon && <span className="grid size-10 place-items-center rounded-lg bg-accent-soft text-signal"><Icon aria-hidden className="size-5" /></span>}
      <h3 className="text-lg">{title}</h3>
      {children && <p className="max-w-[52ch] text-muted-foreground">{children}</p>}
      {action}
    </div>
  )
}

export function ErrorState({ error, retry }: { error: unknown; retry?: () => void }) {
  const message = error instanceof Error ? error.message : String(error)
  return (
    <div role="alert" className="flex flex-wrap items-start justify-between gap-4 rounded-xl border border-error/30 bg-error-soft px-5 py-4">
      <div className="space-y-1">
        <p className="font-ui font-semibold text-error">Couldn’t load this</p>
        <p className="text-muted-foreground">{message.includes('fetch') ? 'The API isn’t reachable. Start it on port 8000, then retry.' : message}</p>
      </div>
      {retry && <Button type="button" size="sm" variant="outline" onClick={retry}>Retry</Button>}
    </div>
  )
}

export function RowsSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-2" aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => <div key={i} className="py-3"><Skeleton className="h-5 w-full rounded-md bg-well" /></div>)}
    </div>
  )
}

/** The page head: a serif title, one line of what the page is for, actions on the right. */
export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: React.ReactNode }) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-x-8 gap-y-3">
      <div className="space-y-1.5">
        <h1 className="text-4xl leading-tight">{title}</h1>
        {description && <p className="max-w-[62ch] text-ink-soft">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </header>
  )
}
