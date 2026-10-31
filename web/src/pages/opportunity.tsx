import { useQuery } from '@tanstack/react-query'
import { BookOpen, CircleCheck, CircleDashed, CircleHelp, CircleX, FilePenLine, FileSearch, GraduationCap, MapPin, ShieldCheck, TriangleAlert, type LucideIcon } from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Breadcrumbs, Checked, claimStatus, isVerified, SourceLink, SourceList, type Claim } from '@/components/app/evidence'
import { TrackButton } from '@/components/app/opportunity-sheet'
import { DeadlineChip, Meter, Pill } from '@/components/app/pills'
import { ErrorState, RowsSkeleton } from '@/components/app/states'
import { Button } from '@/components/ui/button'
import { api, type CheckStatus, type OpportunityDetail, type ProgramEvidence } from '@/lib/api'
import { COUNTRY, DEGREE, eligibility, formatDate, funding } from '@/lib/format'
import { cn } from '@/lib/utils'

const SCORE_ROWS = [
  ['research', 'Research fit', 35], ['funding', 'Funding viability', 25], ['eligibility', 'Academic eligibility', 20],
  ['availability', 'Position availability', 10], ['timing', 'Timing', 10],
] as const

const CHECK: Record<CheckStatus, { word: string; icon: LucideIcon; className: string }> = {
  ok: { word: 'Met', icon: CircleCheck, className: 'text-success' },
  warn: { word: 'Check', icon: CircleHelp, className: 'text-warning' },
  unknown: { word: 'Unknown', icon: CircleDashed, className: 'text-muted-foreground' },
  fail: { word: 'Not met', icon: CircleX, className: 'text-error' },
}

// The funding package split into the parts the spec asks for; a general "funding is available" never fills them in.
const FUNDING_ROWS: { label: string; pick: (e: ProgramEvidence) => boolean }[] = [
  { label: 'Guaranteed funding', pick: (e) => e.field === 'guaranteed_funding' },
  { label: 'Tuition coverage', pick: (e) => e.field === 'tuition_coverage' },
  { label: 'Stipend', pick: (e) => e.field === 'stipend_amount' },
  { label: 'Research assistantship', pick: (e) => e.field === 'funding_sources' && /research assist/i.test(e.value ?? '') },
  { label: 'Teaching assistantship', pick: (e) => e.field === 'funding_sources' && /teaching assist/i.test(e.value ?? '') },
  { label: 'Scholarships and fellowships', pick: (e) => e.field === 'funding_sources' && /scholar|fellow|award/i.test(e.value ?? '') },
  { label: 'Duration', pick: (e) => e.field === 'funding_duration_years' },
  { label: 'International students', pick: (e) => e.field === 'funding_for_international_students' },
  { label: 'Conditions', pick: (e) => e.field === 'funding_conditions' },
]

const toClaim = (e: ProgramEvidence): Claim => ({ field: e.field, value: e.value, quote: e.quote, status: e.status, url: e.source_url, checkedAt: e.checked_at })
const lastChecked = (ev: ProgramEvidence[]) => ev.map((e) => e.checked_at ?? '').sort().at(-1) || null

function Section({ id, title, icon: Icon, children, aside }: { id: string; title: string; icon?: LucideIcon; children: React.ReactNode; aside?: React.ReactNode }) {
  return (
    <section aria-labelledby={id} className="sheet p-5 sm:p-6">
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h2 id={id} className="flex items-center gap-2 text-xl">{Icon && <Icon aria-hidden className="size-5 text-signal" />}{title}</h2>
        {aside}
      </div>
      {children}
    </section>
  )
}

function FundingTable({ d }: { d: OpportunityDetail }) {
  const value = (label: string, items: ProgramEvidence[]) => {
    if (label === 'Stipend' && d.stipend) return d.stipend
    if (label === 'Duration') return items[0]?.value ? `${items[0].value} years` : null
    return [...new Set(items.map((e) => e.value))].join('; ')
  }
  return (
    <table className="w-full text-left text-sm">
      <thead className="sr-only"><tr><th>Part</th><th>What the official pages say</th><th>Source</th></tr></thead>
      <tbody>
        {FUNDING_ROWS.map(({ label, pick }) => {
          const items = d.program_evidence.filter(pick)
          const verified = items.some((e) => isVerified(e.status))
          const v = items.length ? value(label, items) : null
          return (
            <tr key={label} className="border-t border-border align-baseline first:border-t-0">
              <th scope="row" className="w-44 py-2.5 pr-4 font-medium text-foreground">{label}</th>
              <td className="py-2.5 pr-4">
                {v ? <span className="text-foreground">{v}</span> : <span className="text-muted-foreground">Not stated on an official page</span>}
                {items.length > 0 && !verified && <span className="ml-2 text-xs font-medium text-warning" title={claimStatus(items[0].status).hint}>Unverified</span>}
              </td>
              <td className="hidden w-48 py-2.5 text-right sm:table-cell">{items[0]?.source_url && <SourceLink url={items[0].source_url} className="max-w-48 text-xs">{new URL(items[0].source_url).hostname.replace(/^www\./, '')}</SourceLink>}</td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

function DecisionPanel({ d }: { d: OpportunityDetail }) {
  const f = funding(d.funding_status)
  const e = eligibility(d.eligibility_status)
  const fundingConfirmed = d.funding_status === 'confirmed_full' || d.funding_status === 'confirmed_partial'
  const rows: [string, React.ReactNode][] = [
    ['Academic eligibility', <Pill tone={e.tone}>{e.label}</Pill>],
    ['Funding confidence', <Pill tone={f.tone} title={f.hint}>{f.label}</Pill>],
    ['Position availability', <span className="num text-sm text-foreground">{Math.round(d.scores.availability)} / 100</span>],
    ['Deadline', <DeadlineChip date={d.deadline} />],
    ['Last verified', <Checked at={lastChecked(d.program_evidence)} className="text-sm" />],
  ]
  return (
    <aside aria-label="Decision summary" className="sheet space-y-5 p-5 max-lg:order-first lg:sticky lg:top-6">
      <div>
        <p className="text-sm text-muted-foreground">Research fit</p>
        <p className="num text-3xl font-semibold text-foreground">{Math.round(d.scores.research)}<span className="text-lg font-normal text-muted-foreground"> / 100</span></p>
        <Meter value={d.scores.research} label="Research fit" hideValue className="mt-2" />
      </div>
      <dl className="divide-y divide-border border-y border-border">
        {rows.map(([label, value], i) => (
          <div key={i} className="flex items-center justify-between gap-3 py-2.5">
            <dt className="text-sm text-muted-foreground">{label}</dt><dd>{value}</dd>
          </div>
        ))}
      </dl>
      {!fundingConfirmed && (
        <p role="note" className="flex gap-2 rounded-lg bg-warning-soft px-3 py-2.5 text-sm text-foreground">
          <TriangleAlert aria-hidden className="mt-0.5 size-4 shrink-0 text-warning" />
          Funding has not been confirmed on an official page. Ask the department or professor before relying on it.
        </p>
      )}
      <div className="space-y-2">
        <TrackButton d={d} className="w-full" />
        <Button variant="outline" className="w-full" asChild><Link to={`/drafts?for=${d.id}`}><FilePenLine />Draft email</Link></Button>
        {d.program_url && <Button variant="ghost" className="w-full" asChild><a href={d.program_url} target="_blank" rel="noreferrer">Open official program page<span className="sr-only"> (opens a new tab)</span></a></Button>}
      </div>
      <details>
        <summary className="cursor-pointer text-sm text-ink-soft hover:text-foreground">How the ranking is built</summary>
        <table className="mt-2 w-full text-left text-sm">
          <tbody>
            {SCORE_ROWS.map(([key, label, weight]) => (
              <tr key={key}>
                <td className="py-1.5 pr-2 text-foreground">{label} <span className="text-xs text-muted-foreground">{weight}%</span></td>
                <td className="w-28 py-1.5"><Meter value={d.scores[key]} label={label} /></td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-2 text-xs text-muted-foreground">Overall {Math.round(d.overall_score)}. An internal ranking assessment, not a prediction of admission.</p>
      </details>
    </aside>
  )
}

export function OpportunityPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const q = useQuery({ queryKey: ['opportunity', id], queryFn: () => api.opportunity(id!) })
  const profile = useQuery({ queryKey: ['profile'], queryFn: api.profile, retry: false })
  // Back to Discover keeps its filters when we came from there.
  const back = () => ((window.history.state?.idx ?? 0) > 0 ? navigate(-1) : navigate('/opportunities'))

  if (q.isError) return <ErrorState error={q.error} retry={() => q.refetch()} />
  if (!q.data) return <RowsSkeleton rows={8} />
  const d = q.data
  const matches = d.explanation.research_matches ?? []
  const checks = d.explanation.eligibility_checks ?? []
  const matched = new Set(matches.map((m) => m.interest))
  const gaps = (profile.data?.research_interests ?? []).filter((i) => !matched.has(i))
  const prereqs = (d.requirements.prerequisites as string[] | undefined) ?? []
  const kinds = Object.fromEntries((d.requirements.pages ?? []).map((p) => [p.url, p.result.match(/\((\w+)\)/)?.[1]?.replace(/_/g, ' ') ?? p.result]))

  return (
    <div className="space-y-6">
      <Breadcrumbs items={[{ label: 'Discover', onClick: back }, { label: d.university }, { label: d.professor }]} />

      <header className="flex flex-wrap items-end justify-between gap-x-8 gap-y-4">
        <div className="min-w-0 space-y-2">
          <p className="flex items-center gap-1.5 text-sm text-muted-foreground"><MapPin aria-hidden className="size-4" />{d.university}{d.country ? `, ${COUNTRY[d.country] ?? d.country}` : ''}</p>
          <h1 className="text-4xl leading-tight">{d.title}</h1>
          <p className="text-ink-soft">
            <Link to={`/researchers/${d.professor_id}`} className="ink-link">{d.professor}</Link>
            {' · '}{DEGREE[d.degree_type]}{d.requirements.deadline_term ? ` · ${d.requirements.deadline_term as string} intake` : ''}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <TrackButton d={d} />
          <Button variant="outline" asChild><Link to={`/drafts?for=${d.id}`}><FilePenLine />Draft email</Link></Button>
        </div>
      </header>

      {d.excluded_reason && (
        <p role="note" className="rounded-lg border border-error/30 bg-error-soft px-4 py-3 text-foreground">
          <span className="font-semibold text-error">Ruled out. </span>
          {checks.filter((c) => c.status === 'fail').map((c) => c.detail).join(' ') || d.excluded_reason}
        </p>
      )}

      <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(280px,1fr)]">
        <div className="space-y-6">
          <Section id="overview" title="Opportunity overview" icon={GraduationCap}>
            <dl className="grid gap-x-8 gap-y-4 sm:grid-cols-2">
              {([
                ['Degree', DEGREE[d.degree_type]],
                ['Program', d.program],
                ['University', d.university],
                ['Research area', matches[0]?.interest ?? '—'],
                ['Deadline', d.deadline ? formatDate(d.deadline, { month: 'long', day: 'numeric', year: 'numeric' }) : 'Not listed'],
                ['Application', d.program_url ? <SourceLink url={d.program_url}>Official program page</SourceLink> : 'No official link found'],
              ] as [string, React.ReactNode][]).map(([label, value]) => (
                <div key={label}><dt className="text-xs text-muted-foreground">{label}</dt><dd className="mt-0.5 text-foreground">{value}</dd></div>
              ))}
            </dl>
          </Section>

          <Section id="alignment" title="Research alignment" icon={BookOpen}
            aside={<span className="text-xs text-muted-foreground">Compared against {d.professor}’s publications</span>}>
            {matches.length === 0 ? <p className="text-muted-foreground">No publications compared yet. Refresh the professor’s publications from their profile.</p> : (
              <ol className="space-y-3">
                {matches.map((m) => (
                  <li key={m.interest} className="rounded-lg border border-border p-3.5">
                    <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                      <p className="text-sm font-medium text-signal">Your interest: {m.interest}</p>
                      <span className="num text-xs text-muted-foreground" title="Cosine similarity between your interest and the paper">similarity {m.similarity.toFixed(2)}</span>
                    </div>
                    <p className="mt-1 text-foreground">{m.paper}{m.year && <span className="num ml-2 text-sm text-muted-foreground">{m.year}</span>}</p>
                  </li>
                ))}
              </ol>
            )}
            {gaps.length > 0 && (
              <div className="mt-4 rounded-lg bg-well px-4 py-3">
                <p className="text-sm font-medium text-foreground">Potential gaps</p>
                <p className="mt-0.5 text-sm text-muted-foreground">No close publication for: {gaps.join(', ')}.</p>
              </div>
            )}
          </Section>

          <Section id="funding" title="Funding assessment" icon={ShieldCheck}
            aside={<Pill tone={funding(d.funding_status).tone} title={funding(d.funding_status).hint}>{funding(d.funding_status).label}</Pill>}>
            <p className="mb-4 text-ink-soft">{d.funding_explanation}</p>
            <FundingTable d={d} />
          </Section>

          <Section id="eligibility" title="Eligibility" icon={CircleCheck}
            aside={<Pill tone={eligibility(d.eligibility_status).tone}>{eligibility(d.eligibility_status).label}</Pill>}>
            <ul className="divide-y divide-border">
              {checks.map((c) => {
                const k = CHECK[c.status]
                return (
                  <li key={c.name} className="grid grid-cols-[8rem_6rem_1fr] items-baseline gap-3 py-2.5 text-sm max-sm:grid-cols-[1fr_auto]">
                    <span className="font-medium text-foreground capitalize">{c.name}</span>
                    <span className={cn('inline-flex items-center gap-1 font-medium', k.className)}><k.icon aria-hidden className="size-3.5" />{k.word}</span>
                    <span className="text-ink-soft max-sm:col-span-2">{c.detail}</span>
                  </li>
                )
              })}
            </ul>
            {prereqs.length > 0 && (
              <div className="mt-4">
                <p className="text-sm font-medium text-foreground">Degree prerequisites</p>
                <ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm text-ink-soft">{prereqs.map((p) => <li key={p}>{p}</li>)}</ul>
              </div>
            )}
          </Section>

          <Section id="sources" title="Sources and evidence" icon={FileSearch}
            aside={<span className="text-xs text-muted-foreground">Every fact above comes from one of these pages</span>}>
            <SourceList claims={d.program_evidence.map(toClaim)} kinds={kinds} />
          </Section>
        </div>

        <DecisionPanel d={d} />
      </div>
    </div>
  )
}
