import { AlertTriangle, type LucideIcon } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'

export function EmptyState({ icon: Icon, title, children, action }: { icon: LucideIcon; title: string; children?: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed px-6 py-12 text-center">
      <div className="rounded-full bg-muted p-3"><Icon aria-hidden className="size-5 text-muted-foreground" /></div>
      <div className="space-y-1">
        <p className="font-medium">{title}</p>
        {children && <p className="mx-auto max-w-sm text-sm text-muted-foreground">{children}</p>}
      </div>
      {action}
    </div>
  )
}

export function ErrorState({ error, retry }: { error: unknown; retry?: () => void }) {
  const message = error instanceof Error ? error.message : String(error)
  return (
    <div role="alert" className="flex items-start gap-3 rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm">
      <AlertTriangle aria-hidden className="mt-0.5 size-4 shrink-0 text-destructive" />
      <div className="flex-1 space-y-1">
        <p className="font-medium text-destructive">Couldn’t load this</p>
        <p className="text-muted-foreground">{message.includes('fetch') ? 'The API isn’t reachable. Is it running on port 8000?' : message}</p>
      </div>
      {retry && <Button size="sm" variant="outline" onClick={retry}>Retry</Button>}
    </div>
  )
}

export function RowsSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-2" aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => <Skeleton key={i} className="h-11 w-full" />)}
    </div>
  )
}

export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div className="space-y-1">
        <h1 className="text-3xl font-semibold">{title}</h1>
        {description && <p className="max-w-2xl text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  )
}
