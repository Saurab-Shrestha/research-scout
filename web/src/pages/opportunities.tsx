import { useQuery } from '@tanstack/react-query'
import { ArrowDown, ArrowUp, ArrowUpDown, Search, SearchX } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useOpportunityParam } from '@/components/app/opportunity-sheet'
import { DeadlineChip, Meter, Pill, ScoreBadge } from '@/components/app/pills'
import { EmptyState, ErrorState, PageHeader, RowsSkeleton } from '@/components/app/states'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { api, type Opportunity } from '@/lib/api'
import { COUNTRY, DEGREE, ELIGIBILITY, eligibility, FUNDING, funding } from '@/lib/format'
import { cn } from '@/lib/utils'

type SortKey = 'score' | 'research' | 'deadline' | 'professor'
const SORTERS: Record<SortKey, (a: Opportunity, b: Opportunity) => number> = {
  score: (a, b) => a.overall_score - b.overall_score,
  research: (a, b) => a.scores.research - b.scores.research,
  deadline: (a, b) => (a.deadline ?? '9999').localeCompare(b.deadline ?? '9999'),
  professor: (a, b) => a.professor.localeCompare(b.professor),
}

function FilterSelect({ id, label, value, onChange, options }: { id: string; label: string; value: string; onChange: (v: string) => void; options: [string, string][] }) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id} className="text-xs text-muted-foreground">{label}</Label>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger id={id} className="w-full min-w-36"><SelectValue /></SelectTrigger>
        <SelectContent>
          <SelectItem value="all">All</SelectItem>
          {options.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}
        </SelectContent>
      </Select>
    </div>
  )
}

function SortHead({ k, label, sort, setSort, className }: { k: SortKey; label: string; sort: [SortKey, 'asc' | 'desc']; setSort: (s: [SortKey, 'asc' | 'desc']) => void; className?: string }) {
  const active = sort[0] === k
  const Icon = !active ? ArrowUpDown : sort[1] === 'asc' ? ArrowUp : ArrowDown
  return (
    <TableHead className={className} aria-sort={active ? (sort[1] === 'asc' ? 'ascending' : 'descending') : 'none'}>
      <button className="-mx-2 inline-flex items-center gap-1 rounded px-2 py-1 hover:bg-muted focus-visible:outline-2 focus-visible:outline-ring"
        onClick={() => setSort([k, active && sort[1] === 'desc' ? 'asc' : k === 'deadline' || k === 'professor' ? 'asc' : 'desc'])}>
        {label}<Icon aria-hidden className={cn('size-3.5', !active && 'opacity-40')} />
      </button>
    </TableHead>
  )
}

export function OpportunitiesPage() {
  const q = useQuery({ queryKey: ['opportunities'], queryFn: () => api.opportunities(true) })
  const { open } = useOpportunityParam()
  const [params, setParams] = useSearchParams()
  const get = (k: string, d = 'all') => params.get(k) ?? d
  const set = (k: string, v: string) => setParams((p) => { if (v === 'all' || v === '') p.delete(k); else p.set(k, v); return p }, { replace: true })
  const [sort, setSort] = useState<[SortKey, 'asc' | 'desc']>(['score', 'desc'])
  const showExcluded = params.get('excluded') === '1'
  const text = get('q', '').toLowerCase()

  const rows = useMemo(() => {
    const filtered = (q.data ?? []).filter((o) =>
      (showExcluded || !o.excluded_reason)
      && (get('degree') === 'all' || o.degree_type === get('degree'))
      && (get('country') === 'all' || o.country === get('country'))
      && (get('funding') === 'all' || o.funding_status === get('funding'))
      && (get('elig') === 'all' || o.eligibility_status === get('elig'))
      && (!text || `${o.professor} ${o.university} ${o.program}`.toLowerCase().includes(text)))
    const dir = sort[1] === 'asc' ? 1 : -1
    return filtered.sort((a, b) => dir * SORTERS[sort[0]](a, b))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q.data, params, sort])
  const hidden = (q.data ?? []).filter((o) => o.excluded_reason).length

  return (
    <div className="space-y-6">
      <PageHeader title="Discover Opportunities" description="Every professor × degree we’ve checked, ranked by research fit, funding, eligibility, availability and timing." />

      <div className="flex flex-wrap items-end gap-3 rounded-xl border bg-card p-3">
        <div className="min-w-56 flex-1 space-y-1.5">
          <Label htmlFor="q" className="text-xs text-muted-foreground">Search</Label>
          <div className="relative">
            <Search aria-hidden className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input id="q" placeholder="Professor, university or program" className="pl-8" value={get('q', '')} onChange={(e) => set('q', e.target.value)} />
          </div>
        </div>
        <FilterSelect id="degree" label="Degree" value={get('degree')} onChange={(v) => set('degree', v)} options={Object.entries(DEGREE)} />
        <FilterSelect id="country" label="Country" value={get('country')} onChange={(v) => set('country', v)} options={Object.entries(COUNTRY)} />
        <FilterSelect id="funding" label="Funding" value={get('funding')} onChange={(v) => set('funding', v)} options={Object.entries(FUNDING).map(([k, v]) => [k, v.label])} />
        <FilterSelect id="elig" label="Eligibility" value={get('elig')} onChange={(v) => set('elig', v)} options={Object.entries(ELIGIBILITY).map(([k, v]) => [k, v.label])} />
        <div className="flex h-9 items-center gap-2">
          <Checkbox id="excluded" checked={showExcluded} onCheckedChange={(c) => set('excluded', c ? '1' : '')} />
          <Label htmlFor="excluded" className="text-sm font-normal">Show ineligible <span className="text-muted-foreground tabular">({hidden})</span></Label>
        </div>
      </div>

      {q.isError ? <ErrorState error={q.error} retry={() => q.refetch()} /> : q.isLoading ? <RowsSkeleton rows={8} /> : rows.length === 0 ? (
        <EmptyState icon={SearchX} title="No matches" action={<Button variant="outline" onClick={() => setParams({})}>Clear filters</Button>}>Try fewer filters or include ineligible opportunities.</EmptyState>
      ) : (
        <>
          <p className="text-sm text-muted-foreground tabular" aria-live="polite">{rows.length} shown</p>

          <div className="hidden overflow-hidden rounded-xl border bg-card md:block">
            <Table>
              <TableHeader>
                <TableRow className="bg-muted/40 hover:bg-muted/40">
                  <SortHead k="score" label="Score" sort={sort} setSort={setSort} className="w-20 pl-4" />
                  <SortHead k="professor" label="Professor" sort={sort} setSort={setSort} />
                  <TableHead>Degree</TableHead>
                  <TableHead>Funding</TableHead>
                  <SortHead k="deadline" label="Deadline" sort={sort} setSort={setSort} />
                  <TableHead>Eligibility</TableHead>
                  <SortHead k="research" label="Research fit" sort={sort} setSort={setSort} className="w-40 pr-4" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((o) => {
                  const f = funding(o.funding_status), e = eligibility(o.eligibility_status)
                  return (
                    <TableRow key={o.id} className={cn('cursor-pointer', o.excluded_reason && 'opacity-60')} onClick={() => open(o.id)}>
                      <TableCell className="pl-4"><ScoreBadge score={o.overall_score} /></TableCell>
                      <TableCell>
                        <button className="text-left font-medium hover:underline focus-visible:outline-2 focus-visible:outline-ring" onClick={(ev) => { ev.stopPropagation(); open(o.id) }}>{o.professor}</button>
                        <p className="max-w-64 truncate text-xs text-muted-foreground">{o.university} · {COUNTRY[o.country ?? ''] ?? o.country}</p>
                      </TableCell>
                      <TableCell className="text-sm">{DEGREE[o.degree_type]}</TableCell>
                      <TableCell><Pill tone={f.tone} title={f.hint}>{f.label}</Pill>{o.stipend && <p className="mt-1 text-xs text-muted-foreground tabular">{o.stipend}</p>}</TableCell>
                      <TableCell><DeadlineChip date={o.deadline} /></TableCell>
                      <TableCell><Pill tone={e.tone}>{e.label}</Pill></TableCell>
                      <TableCell className="pr-4"><Meter value={o.scores.research} label={`Research fit for ${o.professor}`} /></TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </div>

          <ul className="space-y-2 md:hidden">
            {rows.map((o) => {
              const f = funding(o.funding_status), e = eligibility(o.eligibility_status)
              return (
                <li key={o.id}>
                  <button onClick={() => open(o.id)} className={cn('flex w-full flex-col gap-2 rounded-xl border bg-card p-3 text-left', o.excluded_reason && 'opacity-60')}>
                    <div className="flex items-center gap-3">
                      <ScoreBadge score={o.overall_score} />
                      <div className="min-w-0"><p className="truncate font-medium">{o.professor}</p><p className="truncate text-xs text-muted-foreground">{o.university} · {DEGREE[o.degree_type]}</p></div>
                    </div>
                    <div className="flex flex-wrap gap-2"><Pill tone={f.tone}>{f.label}</Pill><Pill tone={e.tone}>{e.label}</Pill><DeadlineChip date={o.deadline} compact /></div>
                  </button>
                </li>
              )
            })}
          </ul>
        </>
      )}
    </div>
  )
}
