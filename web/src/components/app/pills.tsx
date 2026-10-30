import { cn } from '@/lib/utils'
import type { Tone } from '@/lib/format'
import { daysUntil, formatDate, relativeDays, urgencyTone } from '@/lib/format'
import { CalendarClock } from 'lucide-react'

const TONE: Record<Tone, string> = {
  success: 'bg-success/12 text-success ring-success/25 dark:bg-success/15',
  info: 'bg-info/12 text-info ring-info/25 dark:bg-info/15',
  warning: 'bg-warning/18 text-warning-foreground ring-warning/40 dark:bg-warning/15 dark:text-warning',
  danger: 'bg-destructive/10 text-destructive ring-destructive/25 dark:bg-destructive/15',
  neutral: 'bg-muted text-muted-foreground ring-border',
}
const DOT: Record<Tone, string> = {
  success: 'bg-success', info: 'bg-info', warning: 'bg-warning', danger: 'bg-destructive', neutral: 'bg-muted-foreground/60',
}

export function Pill({ tone, children, className, title }: { tone: Tone; children: React.ReactNode; className?: string; title?: string }) {
  return (
    <span title={title} className={cn('inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset', TONE[tone], className)}>
      <span aria-hidden className={cn('size-1.5 rounded-full', DOT[tone])} />
      {children}
    </span>
  )
}

export function DeadlineChip({ date, compact }: { date: string | null; compact?: boolean }) {
  const days = daysUntil(date)
  if (!date) return <span className="text-xs text-muted-foreground">No deadline found</span>
  const tone = urgencyTone(days)
  return (
    <span className="inline-flex items-center gap-1.5 text-sm tabular">
      <CalendarClock aria-hidden className={cn('size-3.5', tone === 'danger' ? 'text-destructive' : tone === 'warning' ? 'text-warning' : 'text-muted-foreground')} />
      <span className="font-medium">{formatDate(date)}</span>
      {!compact && <span className={cn('text-xs', tone === 'danger' ? 'text-destructive' : tone === 'warning' ? 'text-warning-foreground dark:text-warning' : 'text-muted-foreground')}>{relativeDays(days)}</span>}
    </span>
  )
}

export function ScoreBadge({ score }: { score: number }) {
  const tone = score >= 60 ? 'bg-primary text-primary-foreground' : score >= 45 ? 'bg-primary/15 text-primary' : 'bg-muted text-muted-foreground'
  return (
    <span className={cn('inline-flex h-7 min-w-10 items-center justify-center rounded-md px-1.5 text-sm font-semibold tabular', tone)} aria-label={`Score ${Math.round(score)} of 100`}>
      {Math.round(score)}
    </span>
  )
}

export function Meter({ value, label, className }: { value: number; label: string; className?: string }) {
  return (
    <div className={cn('flex items-center gap-2', className)}>
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(value)} aria-label={label}>
        <div className="h-full rounded-full bg-primary transition-[width] duration-300" style={{ width: `${Math.max(2, Math.min(100, value))}%` }} />
      </div>
      <span className="w-7 text-right text-xs tabular text-muted-foreground">{Math.round(value)}</span>
    </div>
  )
}
