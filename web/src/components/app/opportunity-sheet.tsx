import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bookmark, BookmarkCheck, ExternalLink } from 'lucide-react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { api, type CheckStatus, type OpportunityDetail } from '@/lib/api'
import { COUNTRY, DEGREE, eligibility, funding, STATUS_LABEL } from '@/lib/format'
import { cn } from '@/lib/utils'
import { DeadlineChip, Meter, Pill } from './pills'
import { ErrorState } from './states'

export function useOpportunityParam() {
  const [params, setParams] = useSearchParams()
  return {
    id: params.get('opp'),
    open: (id: string) => setParams((p) => { p.set('opp', id); return p }),
    close: () => setParams((p) => { p.delete('opp'); return p }),
  }
}

const CHECK_WORD: Record<CheckStatus, string> = { ok: 'Met', warn: 'Check', unknown: 'Unknown', fail: 'Not met' }
const CHECK_CLASS: Record<CheckStatus, string> = { ok: 'text-foreground', warn: 'text-signal', unknown: 'text-muted-foreground', fail: 'text-error' }
const SCORE_ROWS = [
  ['research', 'Research fit', 35], ['funding', 'Funding', 25], ['eligibility', 'Eligibility', 20],
  ['availability', 'Availability', 10], ['timing', 'Timing', 10],
] as const

export function TrackButton({ d, className }: { d: Pick<OpportunityDetail, 'id'>; className?: string }) {
  const qc = useQueryClient()
  const { data: apps } = useQuery({ queryKey: ['applications'], queryFn: api.applications })
  const tracked = apps?.find((a) => a.opportunity_id === d.id)
  const navigate = useNavigate()
  const save = useMutation({
    mutationFn: () => api.track(d.id),
    onSuccess: (a) => {
      qc.invalidateQueries({ queryKey: ['applications'] })
      toast.success('Added to your shortlist', { description: a.next_action ?? undefined, action: { label: 'View shortlist', onClick: () => navigate('/shortlist') } })
    },
    onError: (e) => toast.error('Couldn’t add it to your shortlist', { description: e.message }),
  })
  if (tracked?.status === 'shortlisted') return <Button variant="outline" className={className} asChild><Link to="/shortlist"><BookmarkCheck />On your shortlist</Link></Button>
  if (tracked) return <Button variant="outline" className={className} asChild><Link to="/tracker">In the tracker: {STATUS_LABEL[tracked.status]}</Link></Button>
  return <Button type="button" className={className} onClick={() => save.mutate()} disabled={save.isPending}><Bookmark />{save.isPending ? 'Saving…' : 'Add to shortlist'}</Button>
}

function Body({ d }: { d: OpportunityDetail }) {
  const f = funding(d.funding_status)
  const e = eligibility(d.eligibility_status)
  const checks = d.explanation.eligibility_checks ?? []
  const matches = d.explanation.research_matches ?? []
  const evidence = d.program_evidence.filter((x) => x.value)
  const pages = d.requirements.pages ?? []
  return (
    <>
      <div className="flex flex-wrap items-center gap-2 px-6 pb-5">
        <TrackButton d={d} />
        <Button variant="outline" asChild><Link to={`/drafts?for=${d.id}`}>Draft an email</Link></Button>
        <Button variant="secondary" asChild><Link to={`/opportunities/${d.id}`}>Full details</Link></Button>
        {d.faculty_url && <a href={d.faculty_url} target="_blank" rel="noreferrer" className="ink-link ml-2 inline-flex items-center gap-1 font-ui text-sm">Faculty page<ExternalLink aria-hidden className="size-3.5" /></a>}
        {d.program_url && <a href={d.program_url} target="_blank" rel="noreferrer" className="ink-link ml-2 inline-flex items-center gap-1 font-ui text-sm">Program page<ExternalLink aria-hidden className="size-3.5" /></a>}
      </div>

      {d.excluded_reason && (
        <p role="note" className="mx-6 rounded-lg border border-error/30 bg-error-soft px-4 py-3 text-foreground">
          <span className="font-ui font-semibold text-error">Ruled out. </span>
          {checks.filter((c) => c.status === 'fail').map((c) => c.detail).join(' ') || d.excluded_reason}
        </p>
      )}

      <Tabs defaultValue="overview" className="px-6 pb-8">
        <TabsList className="w-full justify-start gap-4 border-b border-border">
          <TabsTrigger value="overview" className="flex-none">Overview</TabsTrigger>
          <TabsTrigger value="research" className="flex-none">Research</TabsTrigger>
          <TabsTrigger value="funding" className="flex-none">Funding</TabsTrigger>
          <TabsTrigger value="eligibility" className="flex-none">Eligibility</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-8 pt-5">
          <dl className="grid grid-cols-2 border-t border-border">
            {[
              ['Deadline', <DeadlineChip date={d.deadline} />],
              ['Funding', <><Pill tone={f.tone} title={f.hint}>{f.label}</Pill>{d.stipend && <span className="num ml-2 text-sm">{d.stipend}</span>}</>],
              ['Eligibility', <Pill tone={e.tone}>{e.label}</Pill>],
              ['Program', <span className="text-foreground">{d.program}</span>],
            ].map(([label, value], i) => (
              <div key={i} className={cn('space-y-1 border-b border-border py-3', i % 2 === 1 && 'border-l pl-4')}>
                <dt className="text-sm text-muted-foreground">{label}</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>
          <section aria-labelledby="breakdown">
            <h3 id="breakdown" className="rule-firm pb-2 text-base">Score breakdown</h3>
            <table className="w-full text-left">
              <thead className="sr-only"><tr><th>Factor</th><th>Weight</th><th>Score</th></tr></thead>
              <tbody>
                {SCORE_ROWS.map(([key, label, weight]) => (
                  <tr key={key} className="border-b border-border">
                    <td className="py-2.5 pr-3 text-foreground">{label}</td>
                    <td className="num w-12 py-2.5 pr-4 text-right text-xs text-muted-foreground">{weight}%</td>
                    <td className="w-48 py-2.5"><Meter value={d.scores[key]} label={label} /></td>
                  </tr>
                ))}
                <tr>
                  <td className="py-2.5 pr-3 font-ui font-semibold text-foreground">Overall</td>
                  <td />
                  <td className="num py-2.5 text-right text-base font-medium text-foreground">{Math.round(d.overall_score)}</td>
                </tr>
              </tbody>
            </table>
            <p className="mt-2 text-sm text-muted-foreground">A way to order your shortlist. It does not predict admission.</p>
          </section>
        </TabsContent>

        <TabsContent value="research" className="pt-5">
          {matches.length === 0 ? <p className="text-muted-foreground">No publications compared yet.</p> : (
            <ol className="border-t border-border">
              {matches.map((m) => (
                <li key={m.interest} className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 border-b border-border py-3">
                  <p className="text-sm text-muted-foreground">Your interest: {m.interest}</p>
                  <span className="num row-span-2 self-center text-sm text-ink-soft" title="Cosine similarity of the embeddings">{m.similarity.toFixed(2)}</span>
                  <p className="text-foreground">{m.paper}{m.year && <span className="num ml-2 text-sm text-muted-foreground">{m.year}</span>}</p>
                </li>
              ))}
            </ol>
          )}
        </TabsContent>

        <TabsContent value="funding" className="space-y-6 pt-5">
          <div className="space-y-1.5">
            <Pill tone={f.tone} className="font-ui text-lg font-semibold">{f.label}</Pill>
            <p className="text-ink-soft">{d.funding_explanation}</p>
          </div>
          <section aria-labelledby="evidence">
            <h3 id="evidence" className="rule-firm pb-2 text-base">Evidence from official pages</h3>
            {evidence.length === 0 ? <p className="py-3 text-muted-foreground">No quotes found. The status above is the usual rule for this degree and country.</p> : (
              <ul>
                {evidence.map((x, i) => (
                  <li key={i} className="space-y-1.5 border-b border-border py-3">
                    <div className="flex flex-wrap items-baseline justify-between gap-x-4">
                      <p className="text-foreground"><span className="text-muted-foreground">{x.field.replace(/_/g, ' ')}:</span> {x.value}</p>
                      <span className={cn('text-sm', x.status === 'quote_verified' ? 'text-muted-foreground' : 'text-signal')}
                        title={x.status === 'quote_verified' ? 'Found word for word on the page' : 'Not found word for word on the page'}>
                        {x.status === 'quote_verified' ? 'Quote verified' : 'Unverified'}
                      </span>
                    </div>
                    {x.quote && <blockquote className="border-l border-rule-firm pl-3 text-sm text-ink-soft">“{x.quote}”</blockquote>}
                  </li>
                ))}
              </ul>
            )}
          </section>
          {pages.length > 0 && (
            <details>
              <summary className="cursor-pointer font-ui text-sm text-ink-soft hover:text-foreground">Pages checked ({pages.length})</summary>
              <table className="mt-2 w-full text-left text-sm">
                <tbody>
                  {pages.map((p) => (
                    <tr key={p.url} className="border-t border-border align-baseline">
                      <td className="w-24 py-2 pr-3 text-muted-foreground">{p.result.split(':')[0]}</td>
                      <td className="max-w-0 py-2"><a className="ink-link block truncate" href={p.url} target="_blank" rel="noreferrer">{p.url}</a></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          )}
        </TabsContent>

        <TabsContent value="eligibility" className="pt-5">
          <table className="w-full border-t border-border text-left">
            <thead className="sr-only"><tr><th>Check</th><th>Result</th><th>Detail</th></tr></thead>
            <tbody>
              {checks.map((c) => (
                <tr key={c.name} className="border-b border-border align-baseline">
                  <td className="w-28 py-3 pr-3 capitalize text-foreground">{c.name}</td>
                  <td className={cn('w-20 py-3 pr-3 font-ui text-sm font-medium', CHECK_CLASS[c.status])}>{CHECK_WORD[c.status]}</td>
                  <td className="py-3 text-ink-soft">{c.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </TabsContent>
      </Tabs>
    </>
  )
}

export function OpportunitySheet() {
  const { id, close } = useOpportunityParam()
  const q = useQuery({ queryKey: ['opportunity', id], queryFn: () => api.opportunity(id!), enabled: !!id })
  const d = q.data
  return (
    <Sheet open={!!id} onOpenChange={(o) => !o && close()}>
      <SheetContent side="right" className="w-full gap-0 overflow-y-auto bg-background p-0 sm:max-w-xl">
        <SheetHeader className="px-6 pb-5 pt-7">
          {d ? (
            <div className="grid grid-cols-[1fr_auto] items-start gap-x-6 pr-8">
              <div className="min-w-0 space-y-1">
                <SheetTitle className="font-heading text-2xl font-semibold leading-tight"><Link to={`/researchers/${d.professor_id}`} className="hover:underline">{d.professor}</Link></SheetTitle>
                <SheetDescription className="text-base text-ink-soft">
                  {d.university}, {COUNTRY[d.country ?? ''] ?? d.country}
                  <br />{DEGREE[d.degree_type]}
                </SheetDescription>
              </div>
              <div className="text-right">
                <p className="num text-4xl font-medium leading-none tracking-[-0.04em] text-foreground">{Math.round(d.overall_score)}</p>
                <p className="mt-1 text-xs text-muted-foreground">score of 100</p>
              </div>
            </div>
          ) : (
            <><SheetTitle className="sr-only">Opportunity</SheetTitle><Skeleton className="h-8 w-2/3 rounded-md bg-well" /><Skeleton className="h-4 w-1/2 rounded-md bg-well" /></>
          )}
        </SheetHeader>
        {q.isError && <div className="px-6"><ErrorState error={q.error} retry={() => q.refetch()} /></div>}
        {d && <Body d={d} />}
      </SheetContent>
    </Sheet>
  )
}
