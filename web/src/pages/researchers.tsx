import { useQuery } from '@tanstack/react-query'
import { BookOpen, Building2, Compass, MapPin, Microscope, Search } from 'lucide-react'
import { useMemo } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Meter, Pill } from '@/components/app/pills'
import { EmptyState, ErrorState, PageHeader, RowsSkeleton } from '@/components/app/states'
import { Button } from '@/components/ui/button'
import { api, type Professor } from '@/lib/api'
import { COUNTRY } from '@/lib/format'
import { cn } from '@/lib/utils'

const topicsOf = (p: Professor) => (p.research_summary ?? '').split(/;\s*/).map((t) => t.trim().toLowerCase()).filter(Boolean)
const RECRUITING = { yes: 'Says accepting students', no: 'Not accepting', unknown: 'No statement found' } as const
const recruitingKey = (p: Professor) => (p.accepting_students === true ? 'yes' : p.accepting_students === false ? 'no' : 'unknown')

const SORTS = { fit: 'Best research fit', recent: 'Most recent publications', name: 'Name' } as const
type SortKey = keyof typeof SORTS

const selectClass = 'h-9 rounded-lg border border-input bg-sheet px-2.5 text-sm text-foreground focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-ring'

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="flex flex-col gap-1.5 text-xs font-medium text-muted-foreground">{label}{children}</label>
}

export function ResearchersPage() {
  const profs = useQuery({ queryKey: ['professors', 'directory'], queryFn: () => api.professors(200) })
  const opps = useQuery({ queryKey: ['opportunities'], queryFn: () => api.opportunities(true) })
  const [params, setParams] = useSearchParams()
  const get = (k: string) => params.get(k) ?? ''
  const set = (k: string, v: string) => setParams((p) => { if (v) p.set(k, v); else p.delete(k); return p }, { replace: true })
  const sort = (params.get('sort') as SortKey) in SORTS ? (params.get('sort') as SortKey) : 'fit'

  // Best research-fit score across a professor's evaluated programs; absent until programs are evaluated.
  const fit = useMemo(() => {
    const m = new Map<string, number>()
    for (const o of opps.data ?? []) m.set(o.professor_id, Math.max(m.get(o.professor_id) ?? 0, o.scores.research))
    return m
  }, [opps.data])

  const all = profs.data ?? []
  const topics = useMemo(() => {
    const count = new Map<string, number>()
    for (const p of all) for (const t of topicsOf(p)) count.set(t, (count.get(t) ?? 0) + 1)
    // Only areas several researchers share; one-off phrases make poor filters.
    return [...count.entries()].filter(([, n]) => n > 1).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, 14).map(([t]) => t)
  }, [all])
  const institutions = [...new Set(all.map((p) => p.university).filter((u): u is string => !!u))].sort()

  const text = get('q').toLowerCase()
  const rows = all
    .filter((p) => (!text || `${p.name} ${p.university ?? ''} ${p.research_summary ?? ''} ${p.title ?? ''}`.toLowerCase().includes(text))
      && (!get('topic') || topicsOf(p).includes(get('topic')))
      && (!get('uni') || p.university === get('uni'))
      && (!get('country') || p.country === get('country'))
      && (!get('recruiting') || recruitingKey(p) === get('recruiting')))
    .sort((a, b) => sort === 'name' ? a.name.localeCompare(b.name)
      : sort === 'recent' ? (b.latest_publication_year ?? 0) - (a.latest_publication_year ?? 0) || a.name.localeCompare(b.name)
        : (fit.get(b.id) ?? -1) - (fit.get(a.id) ?? -1))
  const filtered = ['q', 'topic', 'uni', 'country', 'recruiting'].some((k) => params.has(k))

  return (
    <div className="space-y-6">
      <PageHeader title="Researchers" description="Professors whose work overlaps your interests, whether or not they have advertised an opening."
        actions={<Button variant="outline" asChild><Link to="/discover"><Compass />Find more researchers</Link></Button>} />

      <div className="sheet space-y-4 p-4 sm:p-5">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-[minmax(0,2fr)_repeat(3,minmax(0,1fr))]">
          <Field label="Search">
            <span className="relative">
              <Search aria-hidden className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
              <input type="search" value={get('q')} onChange={(e) => set('q', e.target.value)} placeholder="Name, university or research interest"
                className={cn(selectClass, 'w-full pl-9 font-normal placeholder:text-muted-foreground')} />
            </span>
          </Field>
          <Field label="Institution">
            <select value={get('uni')} onChange={(e) => set('uni', e.target.value)} className={selectClass}>
              <option value="">All institutions</option>
              {institutions.map((u) => <option key={u} value={u}>{u}</option>)}
            </select>
          </Field>
          <Field label="Location">
            <select value={get('country')} onChange={(e) => set('country', e.target.value)} className={selectClass}>
              <option value="">USA and Canada</option><option value="US">USA</option><option value="CA">Canada</option>
            </select>
          </Field>
          <Field label="Recruiting signal">
            <select value={get('recruiting')} onChange={(e) => set('recruiting', e.target.value)} className={selectClass}>
              <option value="">Any</option>
              {Object.entries(RECRUITING).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </Field>
        </div>
        {topics.length > 0 && (
          <div role="group" aria-label="Research area" className="flex flex-wrap gap-2">
            {topics.map((t) => (
              <button key={t} type="button" aria-pressed={get('topic') === t} onClick={() => set('topic', get('topic') === t ? '' : t)}
                className={cn('h-7 rounded-full border px-3 text-xs font-medium transition-colors duration-(--dur-micro) focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring',
                  get('topic') === t ? 'border-signal bg-signal text-signal-ink' : 'border-input bg-sheet text-ink-soft hover:border-signal hover:text-foreground')}>
                {t}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
        <p className="text-muted-foreground">
          {rows.length} of {all.length} researchers
          {filtered && <> · <button type="button" onClick={() => setParams(sort === 'fit' ? {} : { sort }, { replace: true })} className="ink-link">Reset filters</button></>}
        </p>
        <label className="flex items-center gap-2 text-muted-foreground">Sort by
          <select value={sort} onChange={(e) => set('sort', e.target.value === 'fit' ? '' : e.target.value)} className={selectClass}>
            {Object.entries(SORTS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
      </div>

      {profs.isError ? <ErrorState error={profs.error} retry={() => profs.refetch()} />
        : profs.isLoading ? <RowsSkeleton rows={6} />
          : all.length === 0 ? (
            <EmptyState icon={Microscope} title="No researchers yet" action={<Button asChild><Link to="/discover">Find researchers</Link></Button>}>
              Search publication data for professors in your research areas.
            </EmptyState>
          ) : rows.length === 0 ? (
            <EmptyState icon={Search} title="No researchers found for this search"
              action={<Button variant="outline" onClick={() => setParams({}, { replace: true })}>Clear filters</Button>}>
              Try a broader research area, or another institution.
            </EmptyState>
          ) : (
            <ul className="sheet divide-y divide-border">
              {rows.map((p) => {
                const score = fit.get(p.id)
                const rk = recruitingKey(p)
                return (
                  <li key={p.id} className="grid gap-x-6 gap-y-3 p-4 sm:p-5 md:grid-cols-[minmax(0,1fr)_11rem]">
                    <div className="min-w-0">
                      <h2 className="font-heading text-lg leading-snug">
                        <Link to={`/researchers/${p.id}`} className="text-foreground hover:text-signal hover:underline">{p.name}</Link>
                      </h2>
                      {p.title && <p className="truncate text-sm text-ink-soft">{p.title}</p>}
                      <p className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted-foreground">
                        <span className="inline-flex items-center gap-1.5"><Building2 aria-hidden className="size-3.5" />{p.university ?? 'University unknown'}</span>
                        {p.country && <span className="inline-flex items-center gap-1.5"><MapPin aria-hidden className="size-3.5" />{COUNTRY[p.country] ?? p.country}</span>}
                        <span className="inline-flex items-center gap-1.5"><BookOpen aria-hidden className="size-3.5" />
                          {p.publication_count ? `${p.publication_count} papers · latest ${p.latest_publication_year ?? 'undated'}` : 'No publications stored'}
                        </span>
                      </p>
                      {topicsOf(p).length > 0 && (
                        <ul className="mt-2.5 flex flex-wrap gap-1.5">
                          {topicsOf(p).slice(0, 4).map((t) => <li key={t} className="rounded-md bg-well px-2 py-0.5 text-xs text-ink-soft">{t}</li>)}
                        </ul>
                      )}
                    </div>
                    <div className="flex flex-wrap items-center gap-3 md:flex-col md:items-stretch">
                      <Pill tone={rk === 'yes' ? 'success' : rk === 'no' ? 'danger' : 'neutral'} className="md:self-start">{RECRUITING[rk]}</Pill>
                      {score !== undefined ? (
                        <div className="min-w-32 flex-1 md:flex-none">
                          <p className="text-xs text-muted-foreground">Potential research fit</p>
                          <Meter value={score} label={`Potential research fit with ${p.name}`} />
                        </div>
                      ) : <p className="text-xs text-muted-foreground">Fit not assessed yet</p>}
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
      <p className="text-xs text-muted-foreground">Recruiting signals come only from statements on faculty pages; publication activity is never read as recruiting.</p>
    </div>
  )
}
