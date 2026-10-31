import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, Bookmark, CalendarDays, Columns3, Download, FilePenLine, Kanban, List, MapPin, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import { DeadlineChip, Meter, Pill } from '@/components/app/pills'
import { EmptyState, ErrorState, PageHeader, RowsSkeleton } from '@/components/app/states'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { api, type Application, type Opportunity } from '@/lib/api'
import { COUNTRY, DEGREE, eligibility, formatDate, funding } from '@/lib/format'
import { cn } from '@/lib/utils'

type Item = { app: Application; opp: Opportunity | undefined }
const MAX_COMPARE = 4

/** The rows of the comparison: each dimension stands alone so trade-offs stay visible and nothing is crowned. */
const DIMENSIONS: { label: string; cell: (i: Item) => React.ReactNode; text: (i: Item) => string }[] = [
  { label: 'University', cell: ({ app }) => app.university, text: ({ app }) => app.university },
  { label: 'Professor', cell: ({ app, opp }) => opp ? <Link to={`/researchers/${opp.professor_id}`} className="ink-link">{app.professor}</Link> : app.professor, text: ({ app }) => app.professor },
  { label: 'Degree', cell: ({ app }) => DEGREE[app.degree_type], text: ({ app }) => DEGREE[app.degree_type] },
  { label: 'Location', cell: ({ app }) => COUNTRY[app.country ?? ''] ?? app.country ?? '—', text: ({ app }) => COUNTRY[app.country ?? ''] ?? app.country ?? '' },
  {
    label: 'Research fit',
    cell: ({ opp }) => opp ? <div className="w-32"><Meter value={opp.scores.research} label="Research fit" /></div> : '—',
    text: ({ opp }) => (opp ? String(Math.round(opp.scores.research)) : ''),
  },
  {
    label: 'Funding',
    cell: ({ opp }) => {
      if (!opp) return '—'
      const f = funding(opp.funding_status)
      return <div className="space-y-1"><Pill tone={f.tone} title={f.hint}>{f.label}</Pill>{opp.stipend && <p className="num text-xs text-muted-foreground">{opp.stipend}</p>}</div>
    },
    text: ({ opp }) => (opp ? `${funding(opp.funding_status).label}${opp.stipend ? ` (${opp.stipend})` : ''}` : ''),
  },
  {
    label: 'Eligibility',
    cell: ({ opp }) => { if (!opp) return '—'; const e = eligibility(opp.eligibility_status); return <Pill tone={e.tone}>{e.label}</Pill> },
    text: ({ opp }) => (opp ? eligibility(opp.eligibility_status).label : ''),
  },
  {
    label: 'Recruitment',
    cell: ({ opp }) => {
      if (!opp) return '—'
      const r = opp.accepting_students
      return <Pill tone={r === true ? 'success' : r === false ? 'danger' : 'neutral'} title="From the faculty page’s own statement">{r === true ? 'Confirmed recruiting' : r === false ? 'Not recruiting' : 'Unknown'}</Pill>
    },
    text: ({ opp }) => (opp?.accepting_students === true ? 'Confirmed recruiting' : opp?.accepting_students === false ? 'Not recruiting' : 'Unknown'),
  },
  { label: 'Deadline', cell: ({ app, opp }) => <DeadlineChip date={opp?.deadline ?? app.deadline} />, text: ({ app, opp }) => opp?.deadline ?? app.deadline ?? '' },
]

function exportCsv(items: Item[]) {
  const esc = (v: string) => `"${v.replace(/"/g, '""')}"`
  const rows = DIMENSIONS.map((d) => [d.label, ...items.map((i) => d.text(i))])
  const blob = new Blob([rows.map((r) => r.map(esc).join(',')).join('\n')], { type: 'text/csv' })
  const a = Object.assign(document.createElement('a'), { href: URL.createObjectURL(blob), download: `shortlist-comparison-${new Date().toISOString().slice(0, 10)}.csv` })
  a.click()
  URL.revokeObjectURL(a.href)
}

function useShortlistActions() {
  const qc = useQueryClient()
  const refresh = () => qc.invalidateQueries({ queryKey: ['applications'] })
  const promote = useMutation({
    mutationFn: (a: Application) => api.updateApplication(a.id, { status: 'researching' }),
    onSuccess: (a) => { refresh(); toast.success('Moved to the tracker', { description: a.next_action ?? 'Now under Researching.' }) },
    onError: (e) => toast.error('Couldn’t move it', { description: e.message }),
  })
  const remove = useMutation({
    mutationFn: (a: Application) => api.deleteApplication(a.id).then(() => a),
    onSuccess: (a) => {
      refresh()
      toast('Removed from your shortlist', {
        description: `${a.professor}, ${a.university}`,
        action: { label: 'Undo', onClick: () => api.track(a.opportunity_id).then(refresh) },
      })
    },
    onError: (e) => toast.error('Couldn’t remove it', { description: e.message }),
  })
  return { promote, remove }
}

function Row({ item, selected, onSelect, disableSelect }: { item: Item; selected: boolean; onSelect: (on: boolean) => void; disableSelect: boolean }) {
  const { app, opp } = item
  const { promote, remove } = useShortlistActions()
  const f = opp && funding(opp.funding_status)
  const e = opp && eligibility(opp.eligibility_status)
  const match = opp?.explanation.research_matches?.[0]
  return (
    <li className={cn('grid gap-4 p-4 sm:grid-cols-[auto_1fr] sm:p-5 xl:grid-cols-[auto_1fr_auto]', selected && 'bg-accent-soft/50')}>
      <Checkbox checked={selected} onCheckedChange={(c) => onSelect(!!c)} disabled={disableSelect && !selected} className="mt-1.5"
        aria-label={`Compare ${app.professor}, ${app.university}`} />
      <div className="min-w-0">
        <h3 className="font-heading text-lg leading-snug">{app.university}</h3>
        <p className="text-sm text-foreground">{app.professor} · {DEGREE[app.degree_type]}{match ? ` · ${match.interest}` : ''}</p>
        <div className="mt-2.5 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-muted-foreground">
          {f && <Pill tone={f.tone} title={f.hint}>{f.label}</Pill>}
          {e && <Pill tone={e.tone}>{e.label}</Pill>}
          {app.country && <span className="inline-flex items-center gap-1.5"><MapPin aria-hidden className="size-3.5" />{COUNTRY[app.country] ?? app.country}</span>}
          <span className="inline-flex items-center gap-1.5"><CalendarDays aria-hidden className="size-3.5" />{(opp?.deadline ?? app.deadline) ? formatDate(opp?.deadline ?? app.deadline, { month: 'short', day: 'numeric', year: 'numeric' }) : 'Deadline not listed'}</span>
        </div>
        {opp && <div className="mt-3 max-w-xs"><Meter value={opp.scores.research} label={`Research fit for ${app.professor}`} /><p className="mt-0.5 text-xs text-muted-foreground">Research fit</p></div>}
      </div>
      <div className="flex flex-wrap items-center gap-2 sm:col-span-2 xl:col-span-1 xl:w-44 xl:flex-col xl:items-stretch">
        <Button asChild><Link to={`/opportunities/${app.opportunity_id}`}>View details <ArrowRight data-icon="inline-end" /></Link></Button>
        <Button variant="outline" asChild><Link to={`/drafts?for=${app.opportunity_id}`}><FilePenLine />Draft email</Link></Button>
        <Button variant="secondary" onClick={() => promote.mutate(app)} disabled={promote.isPending}><Kanban />Move to tracker</Button>
        <Button variant="ghost" className="text-muted-foreground hover:text-error" onClick={() => remove.mutate(app)} disabled={remove.isPending}
          aria-label={`Remove ${app.professor}, ${app.university} from your shortlist`}><Trash2 />Remove</Button>
      </div>
    </li>
  )
}

function Comparison({ items }: { items: Item[] }) {
  return (
    <div className="sheet overflow-x-auto">
      <table className="w-full min-w-[640px] text-left text-sm">
        <caption className="sr-only">Side-by-side comparison of shortlisted opportunities</caption>
        <thead>
          <tr className="border-b border-border">
            <td className="w-44 p-4" />
            {items.map(({ app }) => (
              <th key={app.id} scope="col" className="p-4 align-top font-normal">
                <Link to={`/opportunities/${app.opportunity_id}`} className="font-heading text-base font-semibold text-foreground hover:text-signal hover:underline">{app.university}</Link>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {DIMENSIONS.slice(1).map((d) => (
            <tr key={d.label} className="border-b border-border last:border-b-0">
              <th scope="row" className="bg-well/50 p-4 font-medium text-muted-foreground">{d.label}</th>
              {items.map((i) => <td key={i.app.id} className="p-4 align-middle text-foreground">{d.cell(i)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function ShortlistPage() {
  const apps = useQuery({ queryKey: ['applications'], queryFn: api.applications })
  const opps = useQuery({ queryKey: ['opportunities'], queryFn: () => api.opportunities(true) })
  const [params, setParams] = useSearchParams()
  const view = params.get('view') === 'compare' ? 'compare' : 'list'
  const setView = (v: 'list' | 'compare') => setParams((p) => { if (v === 'list') p.delete('view'); else p.set('view', v); return p }, { replace: true })
  const [selected, setSelected] = useState<string[]>([])

  if (apps.isError) return <ErrorState error={apps.error} retry={() => apps.refetch()} />
  const byId = new Map((opps.data ?? []).map((o) => [o.id, o]))
  const items: Item[] = (apps.data ?? []).filter((a) => a.status === 'shortlisted')
    .map((app) => ({ app, opp: byId.get(app.opportunity_id) }))
    .sort((a, b) => (b.opp?.overall_score ?? 0) - (a.opp?.overall_score ?? 0))
  const chosen = items.filter((i) => selected.includes(i.app.id))
  // Compare what was ticked; with nothing ticked, the first few by rank.
  const compared = chosen.length >= 2 ? chosen : items.slice(0, MAX_COMPARE)

  return (
    <div className="space-y-6">
      <PageHeader title="My Shortlist" description="Your saved research opportunities and graduate positions."
        actions={items.length > 0 && (
          <div role="group" aria-label="View" className="inline-flex rounded-lg border border-border bg-sheet p-0.5">
            {([['list', 'List', List], ['compare', 'Compare', Columns3]] as const).map(([v, label, Icon]) => (
              <button key={v} type="button" aria-pressed={view === v} onClick={() => setView(v)}
                className={cn('inline-flex h-8 items-center gap-1.5 rounded-md px-3 text-sm font-medium focus-visible:outline-2 focus-visible:outline-ring',
                  view === v ? 'bg-signal text-signal-ink' : 'text-muted-foreground hover:text-foreground')}>
                <Icon aria-hidden className="size-4" />{label}
              </button>
            ))}
          </div>
        )} />

      {apps.isLoading ? <RowsSkeleton rows={5} /> : items.length === 0 ? (
        <EmptyState icon={Bookmark} title="Your shortlist is empty" action={<Button asChild><Link to="/opportunities">Discover opportunities</Link></Button>}>
          Open any opportunity and choose “Add to shortlist” to keep it here for comparison.
        </EmptyState>
      ) : view === 'list' ? (
        <>
          <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
            <p className="text-muted-foreground">{items.length} saved · tick 2 to {MAX_COMPARE} to compare them side by side</p>
            <Button variant="outline" size="sm" disabled={chosen.length < 2} onClick={() => setView('compare')}><Columns3 />Compare {chosen.length || ''}</Button>
          </div>
          <ul className="sheet divide-y divide-border">
            {items.map((i) => (
              <Row key={i.app.id} item={i} selected={selected.includes(i.app.id)} disableSelect={selected.length >= MAX_COMPARE}
                onSelect={(on) => setSelected((s) => (on ? [...s, i.app.id] : s.filter((x) => x !== i.app.id)))} />
            ))}
          </ul>
        </>
      ) : (
        <>
          <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
            <p className="text-muted-foreground">
              {chosen.length >= 2 ? `Comparing the ${compared.length} you selected.` : `Comparing your top ${compared.length} by rank. Select others from the list view.`}
            </p>
            <Button variant="outline" size="sm" onClick={() => exportCsv(compared)}><Download />Export comparison</Button>
          </div>
          <Comparison items={compared} />
          <p className="text-xs text-muted-foreground">Each dimension is assessed on its own. Research fit is an internal ranking signal, not predictions of admission.</p>
        </>
      )}
    </div>
  )
}
