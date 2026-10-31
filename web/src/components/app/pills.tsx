import { CircleAlert, CircleCheck, CircleDashed, CircleHelp, CircleX } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { Tone } from '@/lib/format'
import { daysUntil, formatDate, urgencyTone } from '@/lib/format'

// Status is always a word plus an icon on a soft tint, so colour is never the only signal.
// Uncertain states (warning/neutral) stay muted: a "likely" must never read like a "confirmed".
const TONE: Record<Tone, string> = {
  success: 'bg-success-soft text-success',
  info: 'bg-accent-soft text-signal',
  warning: 'bg-warning-soft text-warning',
  danger: 'bg-error-soft text-error',
  neutral: 'bg-well text-muted-foreground',
}
const ICON = { success: CircleCheck, info: CircleAlert, warning: CircleHelp, danger: CircleX, neutral: CircleDashed }

export function Pill({ tone, children, className, title }: { tone: Tone; children: React.ReactNode; className?: string; title?: string }) {
  const Icon = ICON[tone]
  return (
    <span title={title} className={cn('inline-flex h-6 items-center gap-1.5 rounded-md px-2 text-xs font-medium whitespace-nowrap', TONE[tone], className)}>
      <Icon aria-hidden className="size-3.5 shrink-0" />{children}
    </span>
  )
}

/** A date with the days left beside it; close ones are flagged in amber, past ones in red. */
export function DeadlineChip({ date, compact }: { date: string | null; compact?: boolean }) {
  const days = daysUntil(date)
  if (!date) return <span className="text-sm text-muted-foreground">Not listed</span>
  const tone = urgencyTone(days)
  return (
    <span className="inline-flex items-baseline gap-2 whitespace-nowrap">
      <span className="num text-sm text-foreground">{formatDate(date)}</span>
      {!compact && days !== null && (
        <span className={cn('num text-xs', tone === 'danger' ? 'text-error' : tone === 'warning' ? 'text-warning' : 'text-muted-foreground')}>
          {days < 0 ? `${-days}d ago` : `${days}d`}
        </span>
      )}
    </span>
  )
}

export function ScoreBadge({ score }: { score: number }) {
  return (
    <span className={cn('num inline-block min-w-[2ch] text-right text-base font-semibold', score >= 60 ? 'text-foreground' : 'text-ink-soft')}
      aria-label={`Score ${Math.round(score)} of 100`}>
      {Math.round(score)}
    </span>
  )
}

/** A single-series bar: the value as a rounded accent bar on a muted track, the figure beside it. */
export function Meter({ value, label, className, hideValue }: { value: number; label: string; className?: string; hideValue?: boolean }) {
  return (
    <div className={cn('flex items-center gap-3', className)}>
      <div className="relative h-1.5 flex-1 overflow-hidden rounded-full bg-well-2" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(value)} aria-label={label}>
        <div className="absolute inset-y-0 left-0 rounded-full bg-navy" style={{ width: `${Math.max(1, Math.min(100, value))}%` }} />
      </div>
      {!hideValue && <span className="num w-7 text-right text-xs text-muted-foreground">{Math.round(value)}</span>}
    </div>
  )
}
