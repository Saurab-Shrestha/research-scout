import { useQuery } from '@tanstack/react-query'
import { ArrowRight, CheckCircle2, Lock, Sparkles } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useOpportunityParam } from '@/components/app/opportunity-sheet'
import { DeadlineChip, Meter, Pill, ScoreBadge } from '@/components/app/pills'
import { EmptyState, ErrorState, RowsSkeleton } from '@/components/app/states'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { api, CLOSED, type Opportunity } from '@/lib/api'
import { daysUntil, DEGREE, formatDate, funding, relativeDays, urgencyTone } from '@/lib/format'
import { cn } from '@/lib/utils'

function greeting() {
  const h = new Date().getHours()
  return h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening'
}

function Stat({ label, value, hint, to, attention }: { label: string; value: number | string; hint: string; to: string; attention?: boolean }) {
  return (
    <Link to={to} className="group flex flex-col gap-0.5 px-4 py-3 transition-colors duration-150 hover:bg-muted/50 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring sm:px-5">
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd className="flex items-baseline gap-2">
        <span className={cn('text-2xl font-semibold tabular', attention && 'text-warning-foreground dark:text-warning')}>{value}</span>
        <span className="truncate text-xs text-muted-foreground">{hint}</span>
      </dd>
    </Link>
  )
}

/** Failed eligibility checks grouped by reason, so one fix (e.g. taking IELTS) shows how much it unlocks. */
function blockers(opps: Opportunity[]) {
  const map = new Map<string, Opportunity[]>()
  for (const o of opps) {
    for (const c of o.explanation.eligibility_checks ?? []) {
      if (c.status === 'fail') map.set(c.detail, [...(map.get(c.detail) ?? []), o])
    }
  }
  return [...map.entries()].sort((a, b) => b[1].length - a[1].length)
}

export function DashboardPage() {
  const opps = useQuery({ queryKey: ['opportunities'], queryFn: () => api.opportunities(true) })
  const apps = useQuery({ queryKey: ['applications'], queryFn: api.applications })
  const profile = useQuery({ queryKey: ['profile'], queryFn: api.profile, retry: false })
  const { open } = useOpportunityParam()

  if (opps.isError) return <ErrorState error={opps.error} retry={() => opps.refetch()} />
  const all = opps.data ?? []
  const shortlist = all.filter((o) => !o.excluded_reason)
  const active = (apps.data ?? []).filter((a) => !CLOSED.includes(a.status))
  const actions = active.filter((a) => a.next_action).sort((a, b) => (a.next_action_at ?? '9').localeCompare(b.next_action_at ?? '9'))
  const due = actions.filter((a) => (daysUntil(a.next_action_at) ?? 99) <= 2).length
  const upcoming = shortlist.filter((o) => (daysUntil(o.deadline) ?? -1) >= 0)
    .sort((a, b) => a.deadline!.localeCompare(b.deadline!))
  const byDate = Map.groupBy(upcoming, (o) => o.deadline!)
  const soon = upcoming.filter((o) => daysUntil(o.deadline)! <= 45).length
  const blocked = blockers(all)
  const firstName = profile.data?.name.split(' ')[0]

  return (
    <div className="space-y-8">
      <div className="space-y-1">
        <h1 className="text-3xl font-semibold">{greeting()}{firstName ? `, ${firstName}` : ''}</h1>
        <p className="text-sm text-muted-foreground">
          {profile.data?.intended_start_term ? `Applying for ${profile.data.intended_start_term}. ` : ''}
          {opps.isLoading ? 'Loading your opportunities…' : `${shortlist.length} opportunities you can apply to, ${all.length - shortlist.length} hidden as ineligible.`}
        </p>
      </div>

      <dl aria-label="Summary" className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border bg-border lg:grid-cols-4 [&>*]:bg-card">
        <Stat to="/opportunities" label="Shortlist" value={opps.isLoading ? '–' : shortlist.length} hint="eligible or likely" />
        <Stat to="/opportunities" label="Deadlines in 45 days" value={opps.isLoading ? '–' : soon} hint={upcoming[0] ? `next ${formatDate(upcoming[0].deadline)}` : 'none found yet'} attention={soon > 0} />
        <Stat to="/tracker" label="In tracker" value={apps.isLoading ? '–' : active.length} hint={`${active.filter((a) => a.contacted_at).length} contacted`} />
        <Stat to="/tracker" label="Actions due" value={apps.isLoading ? '–' : due} hint="within 2 days" attention={due > 0} />
      </dl>

      <div className="grid gap-6 lg:grid-cols-5 lg:items-start">
        <Card className="lg:col-span-3">
          <CardHeader className="flex flex-row items-start justify-between">
            <div className="space-y-1">
              <CardTitle className="font-sans text-base">Next actions</CardTitle>
              <CardDescription>Suggested steps for opportunities you’re tracking</CardDescription>
            </div>
            <Button variant="ghost" size="sm" asChild><Link to="/tracker">Tracker<ArrowRight aria-hidden /></Link></Button>
          </CardHeader>
          <CardContent>
            {apps.isLoading ? <RowsSkeleton rows={3} /> : actions.length === 0 ? (
              <EmptyState icon={CheckCircle2} title="Nothing to do yet">Save opportunities to the tracker and suggested steps show up here.</EmptyState>
            ) : (
              <ul className="divide-y">
                {actions.slice(0, 6).map((a) => {
                  const days = daysUntil(a.next_action_at)
                  const tone = urgencyTone(days)
                  return (
                    <li key={a.id}>
                      <button onClick={() => open(a.opportunity_id)} className="flex w-full items-center gap-3 rounded-md px-2 py-3 text-left transition-colors hover:bg-muted/60 focus-visible:outline-2 focus-visible:outline-ring">
                        <span aria-hidden className={cn('size-2 shrink-0 rounded-full', tone === 'danger' ? 'bg-destructive' : tone === 'warning' ? 'bg-warning' : 'bg-primary/50')} />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm font-medium">{a.next_action}</span>
                          <span className="block truncate text-xs text-muted-foreground">{a.professor} · {a.university} · {DEGREE[a.degree_type]}</span>
                        </span>
                        <span className={cn('shrink-0 text-xs tabular', tone === 'danger' ? 'font-medium text-destructive' : tone === 'warning' ? 'font-medium text-warning-foreground dark:text-warning' : 'text-muted-foreground')}>
                          {a.next_action_at ? (days! < 0 ? `overdue ${-days!}d` : relativeDays(days)) : 'anytime'}
                        </span>
                      </button>
                    </li>
                  )
                })}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="font-sans text-base">Upcoming deadlines</CardTitle>
            <CardDescription>Programs on your shortlist</CardDescription>
          </CardHeader>
          <CardContent>
            {opps.isLoading ? <RowsSkeleton rows={3} /> : byDate.size === 0 ? (
              <p className="text-sm text-muted-foreground">No confirmed deadlines yet. Many program pages don’t list one until autumn.</p>
            ) : (
              <ol className="relative space-y-4 border-l pl-5">
                {[...byDate.entries()].slice(0, 5).map(([date, items]) => {
                  const days = daysUntil(date)!
                  return (
                    <li key={date} className="relative">
                      <span aria-hidden className={cn('absolute -left-[25px] top-1 size-2.5 rounded-full ring-4 ring-card', days <= 14 ? 'bg-warning' : days <= 45 ? 'bg-primary' : 'bg-muted-foreground/50')} />
                      <p className="text-sm font-medium tabular">{formatDate(date, { weekday: 'short', month: 'short', day: 'numeric' })} <span className="font-normal text-muted-foreground">· {relativeDays(days)}</span></p>
                      <ul className="mt-1 space-y-1">
                        {[...Map.groupBy(items, (o) => `${o.university} ${DEGREE[o.degree_type]}`).entries()].map(([program, group]) => (
                          <li key={program} className="text-sm">
                            <span className="text-foreground/80">{program.replace('University of ', 'U ')}</span>
                            <span className="text-muted-foreground"> · </span>
                            {group.map((o, i) => (
                              <span key={o.id}>
                                {i > 0 && <span className="text-muted-foreground">, </span>}
                                <button onClick={() => open(o.id)} className="text-muted-foreground underline-offset-2 hover:text-foreground hover:underline focus-visible:outline-2 focus-visible:outline-ring">{o.professor}</button>
                              </span>
                            ))}
                          </li>
                        ))}
                      </ul>
                    </li>
                  )
                })}
              </ol>
            )}
          </CardContent>
        </Card>
      </div>

      <section aria-labelledby="top" className="space-y-3">
        <div className="flex items-end justify-between">
          <h2 id="top" className="text-xl font-semibold">Top matches</h2>
          <Button variant="ghost" size="sm" asChild><Link to="/opportunities">All opportunities<ArrowRight aria-hidden /></Link></Button>
        </div>
        {opps.isLoading ? <RowsSkeleton rows={2} /> : shortlist.length === 0 ? (
          <EmptyState icon={Sparkles} title="No opportunities yet" action={<Button asChild><Link to="/discover">Discover professors</Link></Button>}>
            Find professors, then evaluate their programs to see ranked matches.
          </EmptyState>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {shortlist.slice(0, 6).map((o) => {
              const f = funding(o.funding_status)
              return (
                <button key={o.id} onClick={() => open(o.id)}
                  className="group flex flex-col gap-3 rounded-xl border bg-card p-4 text-left shadow-xs transition-[border-color,box-shadow] duration-200 hover:border-primary/40 hover:shadow-sm focus-visible:outline-2 focus-visible:outline-ring">
                  <div className="flex items-start gap-3">
                    <ScoreBadge score={o.overall_score} />
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-medium">{o.professor}</p>
                      <p className="truncate text-sm text-muted-foreground">{o.university} · {DEGREE[o.degree_type]}</p>
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Pill tone={f.tone} title={f.hint}>{f.label}</Pill>
                    <DeadlineChip date={o.deadline} compact />
                  </div>
                  <div className="space-y-1">
                    <p className="text-xs text-muted-foreground">Research fit</p>
                    <Meter value={o.scores.research} label="Research fit" />
                  </div>
                </button>
              )
            })}
          </div>
        )}
      </section>

      {blocked.length > 0 && (
        <section aria-labelledby="blockers" className="space-y-3">
          <h2 id="blockers" className="text-xl font-semibold">What’s holding you back</h2>
          <div className="grid gap-3 md:grid-cols-2">
            {blocked.slice(0, 4).map(([reason, items]) => (
              <Card key={reason} className="gap-3 py-4">
                <CardContent className="flex gap-3 px-4">
                  <div className="h-fit rounded-lg bg-destructive/10 p-2 text-destructive"><Lock aria-hidden className="size-4" /></div>
                  <div className="space-y-1.5">
                    <p className="text-sm font-medium">{reason}</p>
                    <p className="text-sm text-muted-foreground">
                      Blocks <span className="font-semibold text-foreground tabular">{items.length}</span> {items.length === 1 ? 'opportunity' : 'opportunities'}: {[...new Set(items.map((o) => o.university))].slice(0, 4).join(', ')}{new Set(items.map((o) => o.university)).size > 4 ? '…' : ''}
                    </p>
                    <Pill tone="neutral">{items.filter((o) => o.scores.research >= 50).length} with research fit ≥ 50</Pill>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
