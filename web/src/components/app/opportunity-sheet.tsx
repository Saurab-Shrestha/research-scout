import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BookmarkCheck, BookmarkPlus, CheckCircle2, CircleHelp, ExternalLink, PenLine, Quote, TriangleAlert, XCircle } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { api, type CheckStatus, type OpportunityDetail } from '@/lib/api'
import { CHECK_TONE, COUNTRY, DEGREE, eligibility, funding, STATUS_LABEL } from '@/lib/format'
import { DeadlineChip, Meter, Pill, ScoreBadge } from './pills'
import { ErrorState } from './states'

export function useOpportunityParam() {
  const [params, setParams] = useSearchParams()
  return {
    id: params.get('opp'),
    open: (id: string) => setParams((p) => { p.set('opp', id); return p }),
    close: () => setParams((p) => { p.delete('opp'); return p }),
  }
}

const CHECK_ICON: Record<CheckStatus, typeof CheckCircle2> = { ok: CheckCircle2, warn: TriangleAlert, unknown: CircleHelp, fail: XCircle }
const CHECK_COLOR: Record<CheckStatus, string> = { ok: 'text-success', warn: 'text-warning', unknown: 'text-muted-foreground', fail: 'text-destructive' }
const SCORE_ROWS = [
  ['research', 'Research fit', 35], ['funding', 'Funding', 25], ['eligibility', 'Eligibility', 20],
  ['availability', 'Availability', 10], ['timing', 'Timing', 10],
] as const

function TrackButton({ d }: { d: OpportunityDetail }) {
  const qc = useQueryClient()
  const { data: apps } = useQuery({ queryKey: ['applications'], queryFn: api.applications })
  const tracked = apps?.find((a) => a.opportunity_id === d.id)
  const save = useMutation({
    mutationFn: () => api.track(d.id),
    onSuccess: (a) => {
      qc.invalidateQueries({ queryKey: ['applications'] })
      toast.success('Added to tracker', { description: a.next_action ?? undefined })
    },
    onError: (e) => toast.error('Couldn’t add to tracker', { description: e.message }),
  })
  if (tracked) {
    return (
      <Button variant="secondary" asChild>
        <Link to="/tracker"><BookmarkCheck aria-hidden />In tracker · {STATUS_LABEL[tracked.status]}</Link>
      </Button>
    )
  }
  return (
    <Button onClick={() => save.mutate()} disabled={save.isPending}>
      <BookmarkPlus aria-hidden />{save.isPending ? 'Saving…' : 'Save to tracker'}
    </Button>
  )
}

function Body({ d }: { d: OpportunityDetail }) {
  const f = funding(d.funding_status)
  const e = eligibility(d.eligibility_status)
  const checks = d.explanation.eligibility_checks ?? []
  const matches = d.explanation.research_matches ?? []
  const fundingEvidence = d.program_evidence.filter((x) => x.value)
  return (
    <>
      <div className="flex flex-wrap gap-2 border-b px-6 pb-4">
        <TrackButton d={d} />
        <Button variant="outline" asChild>
          <Link to={`/drafts?for=${d.id}`}><PenLine aria-hidden />Draft email</Link>
        </Button>
        {d.faculty_url && <Button variant="ghost" asChild><a href={d.faculty_url} target="_blank" rel="noreferrer">Faculty page<ExternalLink aria-hidden /></a></Button>}
        {d.program_url && <Button variant="ghost" asChild><a href={d.program_url} target="_blank" rel="noreferrer">Program page<ExternalLink aria-hidden /></a></Button>}
      </div>

      {d.excluded_reason && (
        <div role="note" className="mx-6 mt-4 flex gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm">
          <XCircle aria-hidden className="mt-0.5 size-4 shrink-0 text-destructive" />
          <span><span className="font-medium">Hidden from your shortlist:</span> {checks.filter((c) => c.status === 'fail').map((c) => c.detail).join(' ') || d.excluded_reason}</span>
        </div>
      )}

      <Tabs defaultValue="overview" className="px-6 py-4">
        <TabsList className="w-full">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="research">Research</TabsTrigger>
          <TabsTrigger value="funding">Funding</TabsTrigger>
          <TabsTrigger value="eligibility">Eligibility</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-6 pt-4">
          <dl className="grid grid-cols-2 gap-4 text-sm">
            <div className="space-y-1"><dt className="text-muted-foreground">Deadline</dt><dd><DeadlineChip date={d.deadline} /></dd></div>
            <div className="space-y-1"><dt className="text-muted-foreground">Funding</dt><dd><Pill tone={f.tone} title={f.hint}>{f.label}</Pill>{d.stipend && <span className="ml-2 tabular">{d.stipend}</span>}</dd></div>
            <div className="space-y-1"><dt className="text-muted-foreground">Eligibility</dt><dd><Pill tone={e.tone}>{e.label}</Pill></dd></div>
            <div className="space-y-1"><dt className="text-muted-foreground">Program</dt><dd className="font-medium">{d.program}</dd></div>
          </dl>
          <section aria-labelledby="breakdown" className="space-y-3">
            <h3 id="breakdown" className="font-sans text-sm font-semibold">Score breakdown</h3>
            {SCORE_ROWS.map(([key, label, weight]) => (
              <div key={key} className="grid grid-cols-[8rem_1fr] items-center gap-3 text-sm">
                <span className="text-muted-foreground">{label} <span className="text-xs">· {weight}%</span></span>
                <Meter value={d.scores[key]} label={label} />
              </div>
            ))}
            <p className="text-xs text-muted-foreground">A way to prioritise, not a prediction of admission.</p>
          </section>
        </TabsContent>

        <TabsContent value="research" className="space-y-3 pt-4">
          {matches.length === 0 && <p className="text-sm text-muted-foreground">No publications compared yet.</p>}
          {matches.map((m) => (
            <div key={m.interest} className="space-y-2 rounded-lg border p-3">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{m.interest}</span>
                <span className="text-xs tabular text-muted-foreground">similarity {m.similarity.toFixed(2)}</span>
              </div>
              <p className="text-sm font-medium leading-snug">{m.paper} {m.year && <span className="font-normal text-muted-foreground">({m.year})</span>}</p>
            </div>
          ))}
        </TabsContent>

        <TabsContent value="funding" className="space-y-4 pt-4">
          <div className="rounded-lg bg-muted/60 p-3 text-sm">
            <Pill tone={f.tone}>{f.label}</Pill>
            <p className="mt-2 text-muted-foreground">{d.funding_explanation}</p>
          </div>
          <h3 className="font-sans text-sm font-semibold">Evidence from official pages</h3>
          {fundingEvidence.length === 0 && <p className="text-sm text-muted-foreground">No quotes found; the status above is the usual rule for this degree and country.</p>}
          <ul className="space-y-2">
            {fundingEvidence.map((x, i) => (
              <li key={i} className="rounded-lg border p-3 text-sm">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium">{x.field.replace(/_/g, ' ')}: <span className="font-normal">{x.value}</span></span>
                  {x.status === 'quote_verified'
                    ? <Pill tone="success">Quote verified</Pill>
                    : <Pill tone="warning" title="The quote wasn’t found word-for-word on the page">Unverified</Pill>}
                </div>
                {x.quote && <blockquote className="mt-2 flex gap-2 text-muted-foreground"><Quote aria-hidden className="size-3.5 shrink-0 translate-y-0.5" /><span className="italic">{x.quote}</span></blockquote>}
              </li>
            ))}
          </ul>
          {(d.requirements.pages?.length ?? 0) > 0 && (
            <details className="text-sm">
              <summary className="cursor-pointer text-muted-foreground">Pages checked ({d.requirements.pages!.length})</summary>
              <ul className="mt-2 space-y-1">
                {d.requirements.pages!.map((p) => (
                  <li key={p.url} className="flex gap-2">
                    <span className="shrink-0 text-xs text-muted-foreground">{p.result.split(':')[0]}</span>
                    <a className="truncate text-primary underline-offset-2 hover:underline" href={p.url} target="_blank" rel="noreferrer">{p.url}</a>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </TabsContent>

        <TabsContent value="eligibility" className="space-y-2 pt-4">
          {checks.map((c) => {
            const Icon = CHECK_ICON[c.status]
            return (
              <div key={c.name} className="flex gap-3 rounded-lg border p-3 text-sm">
                <Icon aria-hidden className={`mt-0.5 size-4 shrink-0 ${CHECK_COLOR[c.status]}`} />
                <div className="flex-1">
                  <p className="font-medium capitalize">{c.name} <span className="sr-only">({CHECK_TONE[c.status]})</span></p>
                  <p className="text-muted-foreground">{c.detail}</p>
                </div>
              </div>
            )
          })}
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
      <SheetContent side="right" className="w-full gap-0 overflow-y-auto p-0 sm:max-w-xl">
        <SheetHeader className="px-6 pt-6 pb-4">
          {d ? (
            <div className="flex items-start gap-3 pr-8">
              <ScoreBadge score={d.overall_score} />
              <div className="min-w-0 space-y-1">
                <SheetTitle className="font-heading text-2xl leading-tight">{d.professor}</SheetTitle>
                <SheetDescription>{d.university} · {COUNTRY[d.country ?? ''] ?? d.country} · {DEGREE[d.degree_type]}</SheetDescription>
              </div>
            </div>
          ) : (
            <><SheetTitle className="sr-only">Opportunity</SheetTitle><Skeleton className="h-8 w-2/3" /><Skeleton className="h-4 w-1/2" /></>
          )}
        </SheetHeader>
        {q.isError && <div className="px-6"><ErrorState error={q.error} retry={() => q.refetch()} /></div>}
        {d && <Body d={d} />}
      </SheetContent>
    </Sheet>
  )
}
