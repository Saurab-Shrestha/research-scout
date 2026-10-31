import { useQuery } from '@tanstack/react-query'
import { ArrowRight, CalendarDays, Check, ChevronRight, Clock, FilePenLine, MapPin, Microscope, Search, ShieldCheck, Star, Telescope, UserRound, Zap, type LucideIcon } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { CalendarExportButton } from '@/components/app/calendar-export'
import { useOpportunityParam } from '@/components/app/opportunity-sheet'
import { Meter, Pill } from '@/components/app/pills'
import { EmptyState, ErrorState, RowsSkeleton } from '@/components/app/states'
import { Button } from '@/components/ui/button'
import { api, CLOSED, type Degree, type Opportunity, type Profile } from '@/lib/api'
import { COUNTRY, daysUntil, DEGREE, formatDate, funding, relativeDays } from '@/lib/format'
import { cn } from '@/lib/utils'

const greeting = () => { const h = new Date().getHours(); return h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening' }
const VERIFIED = ['confirmed_full', 'confirmed_partial']
const shortUni = (name: string) => name.replace(/^University of /, 'U. of ')
const monogram = (name: string) => name.replace(/\b(of|the|at|and)\b/gi, '').split(/[\s,-]+/).filter(Boolean).map((w) => w[0]).join('').slice(0, 3).toUpperCase()

function SearchHero({ profile }: { profile?: Profile }) {
  const navigate = useNavigate()
  // Filters the hero can hand to Discover, from the study plan; each maps to a real query param there.
  const CHIPS = [
    ...(Object.keys(DEGREE) as Degree[]).filter((d) => (profile?.target_degrees ?? ['thesis_masters', 'phd']).includes(d)).map((d) => ({ key: 'degree', value: d, label: DEGREE[d] })),
    ...(profile?.target_countries ?? ['US', 'CA']).map((c) => ({ key: 'country', value: c, label: COUNTRY[c] ?? c })),
  ]
  const [text, setText] = useState('')
  const [chips, setChips] = useState<Record<string, string>>({})
  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    const p = new URLSearchParams(chips)
    if (text.trim()) p.set('q', text.trim())
    navigate(`/opportunities${p.size ? `?${p}` : ''}`)
  }
  return (
    <section aria-labelledby="hero" className="relative overflow-hidden rounded-xl border border-border bg-[linear-gradient(105deg,var(--color-accent-soft)_0%,var(--color-sheet)_75%)] px-6 py-7 sm:px-8 sm:py-8">
      <Telescope aria-hidden strokeWidth={1} className="pointer-events-none absolute -right-6 -bottom-10 hidden size-64 text-signal/10 lg:block" />
      <h2 id="hero" className="text-[1.75rem] leading-tight sm:text-3xl">Find your next research opportunity.</h2>
      <p className="mt-2 max-w-[56ch] text-ink-soft">Discover professors, research groups and funded graduate positions that match your academic profile.</p>
      <form onSubmit={submit} className="relative mt-6 max-w-3xl space-y-3">
        <div className="flex flex-col gap-3 sm:flex-row">
          <label className="relative flex-1">
            <span className="sr-only">Search opportunities</span>
            <Search aria-hidden className="pointer-events-none absolute top-1/2 left-3.5 size-[18px] -translate-y-1/2 text-muted-foreground" />
            <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Search professors, universities, programs…"
              className="h-11 w-full rounded-lg border border-input bg-sheet pr-3 pl-11 text-[0.9375rem] text-foreground shadow-xs outline-none placeholder:text-muted-foreground focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-ring" />
          </label>
          <Button type="submit" size="lg" className="h-11 px-5">Explore opportunities <ArrowRight data-icon="inline-end" /></Button>
        </div>
        <div className="flex flex-wrap gap-2" role="group" aria-label="Filters">
          {CHIPS.map((c) => {
            const on = chips[c.key] === c.value
            return (
              <button key={c.label} type="button" aria-pressed={on}
                onClick={() => setChips(({ [c.key]: cur, ...rest }) => (cur === c.value ? rest : { ...rest, [c.key]: c.value }))}
                className={cn('h-8 rounded-full border px-3 text-[0.8125rem] font-medium transition-colors duration-(--dur-micro) focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring',
                  on ? 'border-signal bg-signal text-signal-ink' : 'border-input bg-sheet text-ink-soft hover:border-signal hover:text-foreground')}>
                {c.label}
              </button>
            )
          })}
        </div>
      </form>
    </section>
  )
}

function Metric({ icon: Icon, tint, value, label, note, to }: { icon: LucideIcon; tint: string; value: number | string; label: string; note: string; to: string }) {
  return (
    <Link to={to} className="group flex items-center gap-4 px-5 py-4 transition-colors duration-(--dur-micro) hover:bg-well/60 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring sm:px-6">
      <span className={cn('grid size-12 shrink-0 place-items-center rounded-full', tint)}><Icon aria-hidden className="size-6" /></span>
      <span>
        <span className="num block text-[1.75rem] leading-none font-semibold text-foreground">{value}</span>
        <span className="mt-1 block font-medium text-foreground">{label}</span>
        <span className="block text-xs text-muted-foreground">{note}</span>
      </span>
    </Link>
  )
}

function RecommendedRow({ o, onOpen }: { o: Opportunity; onOpen: () => void }) {
  const f = funding(o.funding_status)
  const match = o.explanation.research_matches?.[0]
  return (
    <li className="grid gap-4 p-4 sm:grid-cols-[auto_1fr] sm:p-5 xl:grid-cols-[auto_1fr_auto]">
      <span aria-hidden className="hidden size-16 place-items-center rounded-lg border border-border bg-well font-heading text-xl font-semibold text-navy sm:grid">{monogram(o.university)}</span>
      <div className="min-w-0">
        <h3 className="font-heading text-lg leading-snug">{o.university}</h3>
        <p className="text-sm text-foreground">{o.professor} · {DEGREE[o.degree_type]}{match ? ` · ${match.interest}` : ''}</p>
        {match && <p className="mt-1 line-clamp-1 text-sm text-muted-foreground">Overlaps with “{match.paper}”{match.year ? ` (${match.year})` : ''}</p>}
        <div className="mt-2.5 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-muted-foreground">
          <Pill tone={f.tone} title={f.hint}>{f.label}</Pill>
          {o.country && <span className="inline-flex items-center gap-1.5"><MapPin aria-hidden className="size-3.5" />{COUNTRY[o.country] ?? o.country}</span>}
          <span className="inline-flex items-center gap-1.5"><CalendarDays aria-hidden className="size-3.5" />{o.deadline ? formatDate(o.deadline, { month: 'short', day: 'numeric', year: 'numeric' }) : 'Deadline not listed'}</span>
        </div>
      </div>
      <div className="flex items-center gap-3 sm:col-span-2 xl:col-span-1 xl:w-36 xl:flex-col xl:items-stretch">
        <div className="w-36 rounded-lg bg-well px-3.5 py-2.5">
          <p className="text-xs text-muted-foreground">Research fit</p>
          <p className="num mb-1.5 font-semibold text-foreground">{Math.round(o.scores.research)} <span className="font-normal text-muted-foreground">/ 100</span></p>
          <Meter value={o.scores.research} label={`Research fit for ${o.professor}`} hideValue />
        </div>
        <Button type="button" onClick={onOpen} aria-label={`View details for ${o.professor}, ${o.university}`}>View details <ArrowRight data-icon="inline-end" /></Button>
      </div>
    </li>
  )
}

type Step = { key: string; title: string; detail: string; onClick: () => void; tone: 'due' | 'next' | 'idle' }

function NextSteps({ steps }: { steps: Step[] }) {
  return (
    <section aria-labelledby="steps" className="sheet p-5">
      <h2 id="steps" className="flex items-center gap-2 text-xl"><Zap aria-hidden className="size-5 fill-warning/80 text-warning" />Your next steps</h2>
      {steps.length === 0 ? (
        <p className="mt-3 text-sm text-muted-foreground">Nothing waiting on you. Save an opportunity to the tracker and its next step appears here.</p>
      ) : (
        <ol className="mt-3">
          {steps.map((s, i) => (
            <li key={s.key} className="relative">
              {i < steps.length - 1 && <span aria-hidden className="absolute top-6 bottom-0 left-[7px] w-px bg-border" />}
              <button type="button" onClick={s.onClick} className="group flex w-full items-start gap-3 rounded-lg py-2.5 pr-1 text-left focus-visible:outline-2 focus-visible:outline-ring">
                <span aria-hidden className={cn('mt-1 size-[15px] shrink-0 rounded-full border-2 bg-sheet',
                  s.tone === 'due' ? 'border-warning ring-3 ring-warning/20' : s.tone === 'next' ? 'border-signal ring-3 ring-signal/15' : 'border-rule-firm')} />
                <span className="min-w-0 flex-1">
                  <span className="block font-medium text-foreground group-hover:text-signal">{s.title}</span>
                  <span className="block text-sm text-muted-foreground">{s.detail}</span>
                </span>
                <ChevronRight aria-hidden className="mt-1 size-4 text-muted-foreground group-hover:text-signal" />
              </button>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}

function Deadlines({ items, onOpen }: { items: Opportunity[]; onOpen: (id: string) => void }) {
  return (
    <section aria-labelledby="deadlines" className="sheet p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="deadlines" className="flex items-center gap-2 text-xl"><Clock aria-hidden className="size-5 text-signal" />Upcoming deadlines</h2>
        <CalendarExportButton />
      </div>
      {items.length === 0 ? (
        <p className="mt-3 text-sm text-muted-foreground">No program on your list publishes a deadline yet. Many post them in the autumn.</p>
      ) : (
        <ul className="mt-2 divide-y divide-border">
          {items.map((o) => {
            const days = daysUntil(o.deadline)!
            return (
              <li key={o.id}>
                <button type="button" onClick={() => onOpen(o.id)} className="grid w-full grid-cols-[1fr_auto] gap-x-3 py-2.5 text-left focus-visible:outline-2 focus-visible:outline-ring">
                  <span className="truncate font-medium text-foreground">{shortUni(o.university)}</span>
                  <span className="num text-sm text-foreground">{formatDate(o.deadline)}</span>
                  <span className="truncate text-sm text-muted-foreground">{DEGREE[o.degree_type]} · {o.professor}</span>
                  <span className={cn('num text-right text-xs', days <= 14 ? 'font-medium text-warning' : 'text-muted-foreground')}>{relativeDays(days)}</span>
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}

const QUICK = [
  { to: '/drafts', label: 'Draft a professor email', icon: FilePenLine },
  { to: '/researchers#add', label: 'Find researchers in your areas', icon: Microscope },
  { to: '/profile', label: 'Update your academic profile', icon: UserRound },
]

/** Failed eligibility checks grouped by reason, so one fix (taking IELTS) shows how much it would open up. */
function blockers(opps: Opportunity[]) {
  const map = new Map<string, Opportunity[]>()
  for (const o of opps) {
    for (const c of o.explanation.eligibility_checks ?? []) {
      if (c.status === 'fail') map.set(c.detail, [...(map.get(c.detail) ?? []), o])
    }
  }
  return [...map.entries()].sort((a, b) => b[1].length - a[1].length)
}

/** First-run checklist: shown until every step is done, so a fresh install leads somewhere. */
function GetStarted({ hasProfile, profileLoading, opportunities }: { hasProfile: boolean; profileLoading: boolean; opportunities: number }) {
  const ai = useQuery({ queryKey: ['llm-settings'], queryFn: api.llmSettings })
  const profs = useQuery({ queryKey: ['professors', 'directory'], queryFn: () => api.professors(200) })
  if (profileLoading || !ai.data || !profs.data) return null
  const chat = ai.data.providers.find((p) => p.id === ai.data.provider)
  const aiReady = ai.data.provider === 'openai_compatible' ? !!ai.data.base_url : !!(chat?.key_saved || chat?.key_in_env)
  const steps = [
    { done: aiReady, title: 'Connect an AI provider', detail: 'Gemini, OpenAI, Claude or a local model. Used to read pages and draft emails.', to: '/settings#ai' },
    { done: hasProfile, title: 'Fill in your academic profile', detail: 'Education, tests, research interests and your study plan.', to: '/profile' },
    { done: profs.data.length > 0, title: 'Find researchers', detail: 'Search OpenAlex by research area, or add one professor’s page.', to: '/researchers#add' },
    { done: opportunities > 0, title: 'Evaluate their programs', detail: 'Checks funding, deadlines and requirements, then ranks everything.', to: '/researchers#evaluate' },
  ]
  if (steps.every((s) => s.done)) return null
  const next = steps.findIndex((s) => !s.done)
  return (
    <section aria-labelledby="get-started" className="sheet p-5 sm:p-6">
      <h2 id="get-started" className="text-xl">Get started</h2>
      <p className="mt-1 text-sm text-muted-foreground">Four steps from an empty install to a ranked shortlist.</p>
      <ol className="mt-4 grid gap-2 md:grid-cols-2">
        {steps.map((s, i) => (
          <li key={s.title}>
            <Link to={s.to} className={cn('flex h-full gap-3 rounded-xl border px-4 py-3 transition-colors focus-visible:outline-2 focus-visible:outline-ring',
              i === next ? 'border-signal bg-accent-soft' : 'border-border hover:border-input')}>
              <span className={cn('grid size-6 shrink-0 place-items-center rounded-full text-xs font-semibold', s.done ? 'bg-success text-white' : i === next ? 'bg-signal text-signal-ink' : 'bg-well text-muted-foreground')}>
                {s.done ? <Check aria-hidden className="size-3.5" /> : i + 1}
              </span>
              <span>
                <span className={cn('block text-sm font-medium', s.done ? 'text-muted-foreground line-through' : 'text-foreground')}>{s.title}{s.done && <span className="sr-only"> (done)</span>}</span>
                <span className="block text-xs text-muted-foreground">{s.detail}</span>
              </span>
            </Link>
          </li>
        ))}
      </ol>
    </section>
  )
}

export function DashboardPage() {
  const opps = useQuery({ queryKey: ['opportunities'], queryFn: () => api.opportunities(true) })
  const apps = useQuery({ queryKey: ['applications'], queryFn: api.applications })
  const profile = useQuery({ queryKey: ['profile'], queryFn: api.profile, retry: false })
  const { open } = useOpportunityParam()
  const navigate = useNavigate()

  if (opps.isError) return <ErrorState error={opps.error} retry={() => opps.refetch()} />
  const all = opps.data ?? []
  const shortlist = all.filter((o) => !o.excluded_reason)
  const active = (apps.data ?? []).filter((a) => !CLOSED.includes(a.status))
  const tracked = new Set(active.map((a) => a.opportunity_id))
  const upcoming = shortlist.filter((o) => (daysUntil(o.deadline) ?? -1) >= 0).sort((a, b) => a.deadline!.localeCompare(b.deadline!))
  const verified = shortlist.filter((o) => VERIFIED.includes(o.funding_status)).length
  const blocked = blockers(all)
  const firstName = profile.data?.name?.split(' ')[0]

  // Tracker actions first (soonest due), then funding still to verify on the best untracked matches.
  const steps: Step[] = [
    ...active.filter((a) => a.next_action).sort((a, b) => (a.next_action_at ?? '9').localeCompare(b.next_action_at ?? '9')).map((a): Step => {
      const days = daysUntil(a.next_action_at)
      return { key: a.id, title: a.next_action!, detail: `${shortUni(a.university)} · ${a.professor}${a.next_action_at ? ` · ${relativeDays(days)}` : ''}`, onClick: () => open(a.opportunity_id), tone: days !== null && days <= 2 ? 'due' : 'next' }
    }),
    ...shortlist.filter((o) => !tracked.has(o.id) && !VERIFIED.includes(o.funding_status)).slice(0, 2).map((o): Step => (
      { key: o.id, title: 'Verify funding details', detail: `${shortUni(o.university)} · confirm tuition and stipend coverage`, onClick: () => open(o.id), tone: 'idle' })),
  ].slice(0, 4)

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-4xl leading-tight">{greeting()}{firstName ? `, ${firstName}` : ''}.</h1>
        <p className="mt-1 text-lg text-ink-soft">Your research journey, in one place.</p>
      </header>

      <GetStarted hasProfile={!!profile.data} profileLoading={profile.isLoading} opportunities={all.length} />
      <SearchHero profile={profile.data} />

      <section aria-label="Summary" className="sheet grid divide-y divide-border sm:grid-cols-3 sm:divide-x sm:divide-y-0">
        <Metric to="/opportunities" icon={Telescope} tint="bg-accent-soft text-signal" value={opps.isLoading ? '–' : shortlist.length} label="Potential matches" note="Eligible or likely eligible" />
        <Metric to="/opportunities" icon={ShieldCheck} tint="bg-success-soft text-success" value={opps.isLoading ? '–' : verified} label="Funding verified" note="Confirmed on an official page" />
        <Metric to="/opportunities" icon={CalendarDays} tint="bg-accent-soft text-signal" value={opps.isLoading ? '–' : upcoming.filter((o) => daysUntil(o.deadline)! <= 60).length} label="Upcoming deadlines" note="Next 60 days" />
      </section>

      <div className="grid gap-6 lg:grid-cols-12">
        <section aria-labelledby="recommended" className="lg:col-span-8">
          <div className="mb-3 flex items-baseline justify-between gap-4">
            <h2 id="recommended" className="flex items-center gap-2 text-xl"><Star aria-hidden className="size-5 fill-warning/80 text-warning" />Recommended opportunities</h2>
            <Link to="/opportunities" className="ink-link inline-flex items-center gap-1 text-sm">View all {shortlist.length || ''} <ArrowRight aria-hidden className="size-4" /></Link>
          </div>
          {opps.isLoading ? <RowsSkeleton rows={4} /> : shortlist.length === 0 ? (
            <EmptyState icon={Microscope} title="No opportunities yet" action={<Button asChild><Link to="/researchers#add">Find researchers</Link></Button>}>
              Find professors in your areas, then evaluate their programs to rank them here.
            </EmptyState>
          ) : (
            <>
              {/* Best-ranked degree per professor, so one lab doesn't fill the list. */}
              <ul className="sheet divide-y divide-border">
                {shortlist.filter((o, i) => shortlist.findIndex((x) => x.professor_id === o.professor_id) === i).slice(0, 4).map((o) => <RecommendedRow key={o.id} o={o} onOpen={() => navigate(`/opportunities/${o.id}`)} />)}
              </ul>
              <p className="mt-2 text-xs text-muted-foreground">Ranked by research fit, funding, eligibility, availability and timing. Research fit is an internal ranking signal, not a prediction of admission.</p>
            </>
          )}
        </section>

        <div className="space-y-6 lg:col-span-4">
          {apps.isLoading ? <RowsSkeleton rows={3} /> : <NextSteps steps={steps} />}
          <Deadlines items={upcoming.slice(0, 5)} onOpen={open} />
          <nav aria-label="Quick actions" className="sheet p-2">
            {QUICK.map(({ to, label, icon: Icon }) => (
              <Link key={to} to={to} className="group flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-ink-soft hover:bg-well hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring">
                <Icon aria-hidden className="size-4 text-signal" /><span className="flex-1">{label}</span><ChevronRight aria-hidden className="size-4 text-muted-foreground" />
              </Link>
            ))}
          </nav>
        </div>
      </div>

      {blocked.length > 0 && (
        <section aria-labelledby="blockers" className="sheet px-5 py-5 sm:px-6">
          <h2 id="blockers" className="text-xl">What rules opportunities out</h2>
          <p className="mt-1 max-w-[62ch] text-sm text-muted-foreground">Each line is one requirement you don’t meet yet, with how many opportunities it closes.</p>
          <table className="mt-4 w-full text-left">
            <thead>
              <tr className="border-b border-border text-xs text-muted-foreground">
                <th scope="col" className="py-2 pr-4 font-medium">Requirement</th>
                <th scope="col" className="w-24 py-2 pr-4 text-right font-medium">Closes</th>
                <th scope="col" className="hidden w-32 py-2 pr-4 text-right font-medium sm:table-cell">Fit 50 or more</th>
                <th scope="col" className="hidden py-2 font-medium lg:table-cell">Universities</th>
              </tr>
            </thead>
            <tbody>
              {blocked.slice(0, 5).map(([reason, items]) => {
                const unis = [...new Set(items.map((o) => o.university))]
                return (
                  <tr key={reason} className="border-t border-border align-baseline first:border-t-0">
                    <td className="py-3 pr-4 text-foreground">{reason}</td>
                    <td className="num py-3 pr-4 text-right font-semibold text-foreground">{items.length}</td>
                    <td className="num hidden py-3 pr-4 text-right text-ink-soft sm:table-cell">{items.filter((o) => o.scores.research >= 50).length}</td>
                    <td className="hidden py-3 text-sm text-muted-foreground lg:table-cell">{unis.slice(0, 4).map(shortUni).join(', ')}{unis.length > 4 ? `, and ${unis.length - 4} more` : ''}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </section>
      )}
    </div>
  )
}
