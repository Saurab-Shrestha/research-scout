import { ExternalLink, FileSearch, TriangleAlert } from 'lucide-react'
import { Link } from 'react-router-dom'
import { daysUntil, formatDate } from '@/lib/format'
import { cn } from '@/lib/utils'

/** One extracted claim in a common shape, whichever endpoint it came from. */
export type Claim = { field: string; value: string | null; quote: string; status: string; url: string | null; checkedAt: string | null }

const STATUS: Record<string, { label: string; className: string; hint: string }> = {
  quote_verified: { label: 'Quote verified', className: 'text-success', hint: 'Found word for word on the page' },
  api_record: { label: 'Database record', className: 'text-success', hint: 'Taken from a scholarly database record' },
  quote_not_found: { label: 'Unverified', className: 'text-warning', hint: 'The quote was not found word for word on the page' },
}
export const claimStatus = (s: string) => STATUS[s] ?? { label: s.replace(/_/g, ' '), className: 'text-muted-foreground', hint: '' }
export const isVerified = (s: string) => s === 'quote_verified' || s === 'api_record'

export const fieldLabel = (f: string) => f.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase())

/** "web.cs.toronto.edu/graduate/phd" — enough to recognise a page without the scheme noise. */
export function sourceName(url: string | null) {
  if (!url) return 'Pasted text'
  try { const u = new URL(url); return `${u.hostname.replace(/^www\./, '')}${u.pathname === '/' ? '' : u.pathname.replace(/\/$/, '')}` } catch { return url }
}

/** The external link out of Research Scout, marked as such. */
export function SourceLink({ url, children, className }: { url: string; children?: React.ReactNode; className?: string }) {
  return (
    <a href={url} target="_blank" rel="noreferrer" className={cn('ink-link inline-flex min-w-0 items-center gap-1', className)}>
      <span className="truncate">{children ?? sourceName(url)}</span><ExternalLink aria-hidden className="size-3.5 shrink-0" /><span className="sr-only">(opens a new tab)</span>
    </a>
  )
}

/** "Checked Oct 29" with a stale flag past 45 days: recruiting and funding pages change each cycle. */
export function Checked({ at, className }: { at: string | null; className?: string }) {
  if (!at) return null
  const age = -(daysUntil(at) ?? 0)
  return (
    <span className={cn('inline-flex items-center gap-1 text-xs whitespace-nowrap', age > 45 ? 'text-warning' : 'text-muted-foreground', className)}>
      {age > 45 && <TriangleAlert aria-hidden className="size-3.5" />}
      {age > 45 ? `Last verified ${age} days ago` : `Checked ${formatDate(at)}`}
    </span>
  )
}

/** Every page a set of claims came from, newest first, each claim with its quote. */
export function SourceList({ claims, kinds = {} }: { claims: Claim[]; kinds?: Record<string, string> }) {
  const bySource = [...Map.groupBy(claims, (c) => c.url ?? 'pasted').entries()]
    .sort(([, a], [, b]) => (b[0].checkedAt ?? '').localeCompare(a[0].checkedAt ?? ''))
  if (bySource.length === 0) return <p className="text-sm text-muted-foreground">No sources recorded yet.</p>
  return (
    <ol className="relative space-y-4 border-l border-border pl-5">
      {bySource.map(([key, items]) => {
        const url = items[0].url
        const verified = items.filter((c) => isVerified(c.status)).length
        return (
          <li key={key} className="relative">
            <span aria-hidden className="absolute top-1 -left-[27px] grid size-[13px] place-items-center rounded-full border-2 border-signal bg-sheet" />
            <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
              <p className="flex min-w-0 items-center gap-2 font-medium text-foreground">
                <FileSearch aria-hidden className="size-4 shrink-0 text-muted-foreground" />
                {url ? <SourceLink url={url} /> : 'Pasted text'}
              </p>
              <Checked at={items[0].checkedAt} />
            </div>
            <p className="mt-0.5 text-xs text-muted-foreground">
              {url && kinds[url] ? `${kinds[url]} · ` : ''}{items.length} {items.length === 1 ? 'fact' : 'facts'} extracted, {verified} verified
            </p>
            <details className="group mt-1.5">
              <summary className="cursor-pointer text-sm text-ink-soft hover:text-foreground">Show extracted evidence</summary>
              <ul className="mt-2 space-y-2.5">
                {items.map((c, i) => {
                  const st = claimStatus(c.status)
                  return (
                    <li key={i} className="rounded-lg bg-well px-3 py-2.5 text-sm">
                      <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                        <p className="text-foreground"><span className="text-muted-foreground">{fieldLabel(c.field)}:</span> {c.value}</p>
                        <span className={cn('text-xs font-medium', st.className)} title={st.hint}>{st.label}</span>
                      </div>
                      {c.quote && c.quote !== c.value && <blockquote className="mt-1 border-l-2 border-rule-firm pl-2.5 text-ink-soft">“{c.quote}”</blockquote>}
                    </li>
                  )
                })}
              </ul>
            </details>
          </li>
        )
      })}
    </ol>
  )
}

/** Breadcrumb trail for nested pages; the last item is the current page. */
export function Breadcrumbs({ items }: { items: { label: string; to?: string; onClick?: () => void }[] }) {
  return (
    <nav aria-label="Breadcrumb" className="text-sm text-muted-foreground">
      <ol className="flex flex-wrap items-center gap-1.5">
        {items.map((it, i) => (
          <li key={i} className="flex items-center gap-1.5">
            {i > 0 && <span aria-hidden>/</span>}
            {it.onClick ? <button type="button" onClick={it.onClick} className="hover:text-foreground hover:underline">{it.label}</button>
              : it.to ? <Link to={it.to} className="hover:text-foreground hover:underline">{it.label}</Link>
              : <span aria-current={i === items.length - 1 ? 'page' : undefined} className={i === items.length - 1 ? 'text-foreground' : ''}>{it.label}</span>}
          </li>
        ))}
      </ol>
    </nav>
  )
}
