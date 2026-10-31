import { useQuery } from '@tanstack/react-query'
import { ArrowRight, BookOpen, Building2, FilePenLine, FileSearch, Mail, Megaphone, Microscope, Sparkles, type LucideIcon } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Breadcrumbs, Checked, SourceLink, SourceList, type Claim } from '@/components/app/evidence'
import { Pill } from '@/components/app/pills'
import { ErrorState, RowsSkeleton } from '@/components/app/states'
import { Button } from '@/components/ui/button'
import { api, type Professor, type Publication } from '@/lib/api'
import { DEGREE, funding } from '@/lib/format'
import { cn } from '@/lib/utils'

function Section({ id, title, icon: Icon, children, aside }: { id: string; title: string; icon: LucideIcon; children: React.ReactNode; aside?: React.ReactNode }) {
  return (
    <section aria-labelledby={id} className="sheet p-5 sm:p-6">
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-2">
        <h2 id={id} className="flex items-center gap-2 text-xl"><Icon aria-hidden className="size-5 text-signal" />{title}</h2>
        {aside}
      </div>
      {children}
    </section>
  )
}

const pubLink = (p: Publication) => p.url ?? (p.doi ? `https://doi.org/${p.doi}` : null) ?? p.open_access_url

/** Papers per year as a row of bars: enough to see whether the lab is active now, no more. */
function Activity({ pubs }: { pubs: Publication[] }) {
  const years = pubs.map((p) => p.publication_year).filter((y): y is number => !!y)
  if (years.length === 0) return null
  const now = new Date().getFullYear()
  const span = Array.from({ length: Math.min(8, now - Math.min(...years) + 1) }, (_, i) => now - i).reverse()
  const counts = span.map((y) => years.filter((x) => x === y).length)
  const max = Math.max(1, ...counts)
  return (
    <figure>
      <div className="flex h-16 items-end gap-1.5" role="img" aria-label={`Publications per year: ${span.map((y, i) => `${y}: ${counts[i]}`).join(', ')}`}>
        {counts.map((c, i) => (
          <div key={span[i]} className="flex flex-1 flex-col items-center gap-1">
            <span className="num text-[0.6875rem] text-muted-foreground">{c || ''}</span>
            <div className={cn('w-full rounded-t-sm', c ? 'bg-signal/70' : 'bg-well-2')} style={{ height: `${Math.max(3, (c / max) * 40)}px` }} />
          </div>
        ))}
      </div>
      <div className="mt-1 flex gap-1.5">{span.map((y) => <span key={y} className="num flex-1 text-center text-[0.6875rem] text-muted-foreground">’{String(y).slice(2)}</span>)}</div>
      <figcaption className="mt-2 text-xs text-muted-foreground">Papers per year among the {pubs.length} we hold. Publication activity alone does not mean the lab is recruiting.</figcaption>
    </figure>
  )
}

function Publications({ pubs, relevant }: { pubs: Publication[]; relevant: Map<string, string> }) {
  const [sort, setSort] = useState<'recent' | 'relevant'>('recent')
  const rows = sort === 'recent' ? pubs : [...pubs].sort((a, b) => Number(relevant.has(b.id)) - Number(relevant.has(a.id)))
  return (
    <Section id="publications" title="Publications" icon={BookOpen}
      aside={
        <div role="group" aria-label="Sort publications" className="inline-flex rounded-lg bg-well p-0.5 text-sm">
          {(['recent', 'relevant'] as const).map((k) => (
            <button key={k} type="button" aria-pressed={sort === k} onClick={() => setSort(k)}
              className={cn('rounded-md px-2.5 py-1 font-medium', sort === k ? 'bg-sheet text-foreground shadow-xs' : 'text-muted-foreground hover:text-foreground')}>
              {k === 'recent' ? 'Recent' : 'Relevant to you'}
            </button>
          ))}
        </div>
      }>
      {pubs.length === 0 ? <p className="text-muted-foreground">No publications stored yet.</p> : (
        <ol className="divide-y divide-border">
          {rows.map((p) => {
            const href = pubLink(p)
            const why = relevant.get(p.id)
            return (
              <li key={p.id} className="py-3.5 first:pt-0 last:pb-0">
                <div className="flex items-baseline gap-3">
                  <span className="num w-10 shrink-0 text-sm text-muted-foreground">{p.publication_year ?? '—'}</span>
                  <div className="min-w-0 flex-1">
                    <p className="font-medium text-foreground">{href ? <a href={href} target="_blank" rel="noreferrer" className="hover:text-signal hover:underline">{p.title}<span className="sr-only"> (opens a new tab)</span></a> : p.title}</p>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {p.author_position ? `${p.author_position[0].toUpperCase()}${p.author_position.slice(1)} author` : 'Author'}
                      {p.doi && <> · <span className="mono">doi:{p.doi}</span></>}
                      {p.arxiv_id && !p.doi && <> · <span className="mono">arXiv:{p.arxiv_id}</span></>}
                    </p>
                    {why && <p className="mt-1.5 inline-flex items-center gap-1.5 rounded-md bg-accent-soft px-2 py-0.5 text-xs font-medium text-signal"><Sparkles aria-hidden className="size-3.5" />Matches your interest: {why}</p>}
                    {p.abstract && (
                      <details className="mt-1.5">
                        <summary className="cursor-pointer text-sm text-ink-soft hover:text-foreground">Abstract</summary>
                        <p className="mt-1 text-sm text-ink-soft">{p.abstract}</p>
                      </details>
                    )}
                  </div>
                </div>
              </li>
            )
          })}
        </ol>
      )}
    </Section>
  )
}

/** Recruiting and funding signals, each tied to where it came from; nothing is inferred from publications. */
function Signals({ prof, opps }: { prof: Professor; opps: { id: string; degree_type: keyof typeof DEGREE; funding_status: string; program_url: string | null }[] }) {
  const accepting = prof.evidence.find((e) => e.field_name === 'accepting_students')
  return (
    <ul className="divide-y divide-border">
      <li className="flex flex-wrap items-start justify-between gap-3 py-3 first:pt-0">
        <div>
          <p className="font-medium text-foreground">Recruiting statement</p>
          <p className="text-sm text-muted-foreground">
            {prof.accepting_students === true ? 'Says they are accepting students.' : prof.accepting_students === false ? 'Says they are not accepting students.' : 'No statement found on the faculty page.'}
          </p>
          {accepting?.excerpt && <blockquote className="mt-1 border-l-2 border-rule-firm pl-2.5 text-sm text-ink-soft">“{accepting.excerpt}”</blockquote>}
        </div>
        <div className="text-right">
          <Pill tone={prof.accepting_students === true ? 'success' : prof.accepting_students === false ? 'danger' : 'neutral'}>
            {prof.accepting_students === true ? 'Confirmed recruiting' : prof.accepting_students === false ? 'Not recruiting' : 'Unknown'}
          </Pill>
          {accepting && <><br /><Checked at={accepting.checked_at} /></>}
        </div>
      </li>
      {opps.map((o) => {
        const f = funding(o.funding_status)
        return (
          <li key={o.id} className="flex flex-wrap items-center justify-between gap-3 py-3 last:pb-0">
            <div>
              <p className="font-medium text-foreground">{DEGREE[o.degree_type]} funding</p>
              <p className="text-sm text-muted-foreground">{f.hint}{o.program_url && <> · <SourceLink url={o.program_url}>program page</SourceLink></>}</p>
            </div>
            <div className="flex items-center gap-3">
              <Pill tone={f.tone}>{f.label}</Pill>
              <Link to={`/opportunities/${o.id}`} className="ink-link text-sm">Details</Link>
            </div>
          </li>
        )
      })}
    </ul>
  )
}

export function ResearcherPage() {
  const { id } = useParams()
  const q = useQuery({ queryKey: ['professor', id], queryFn: () => api.professor(id!) })
  const opps = useQuery({ queryKey: ['opportunities'], queryFn: () => api.opportunities(true) })

  if (q.isError) return <ErrorState error={q.error} retry={() => q.refetch()} />
  if (!q.data) return <RowsSkeleton rows={8} />
  const p = q.data
  const mine = (opps.data ?? []).filter((o) => o.professor_id === p.id)
  const best = mine.find((o) => !o.excluded_reason) ?? mine[0]
  const matches = mine.flatMap((o) => o.explanation.research_matches ?? [])
  const relevant = new Map(matches.map((m) => [m.publication_id, m.interest]))
  const topics = (p.research_summary ?? '').split(/;\s*/).filter(Boolean)
  const department = p.evidence.find((e) => e.field_name === 'department')?.value
  const claims: Claim[] = p.evidence.map((e) => ({ field: e.field_name, value: e.value, quote: e.excerpt, status: e.verification_status, url: e.source_url, checkedAt: e.checked_at }))

  return (
    <div className="space-y-6">
      <Breadcrumbs items={[{ label: 'Researchers', to: '/researchers' }, { label: p.name }]} />

      <header className="flex flex-wrap items-end justify-between gap-x-8 gap-y-4">
        <div className="min-w-0 space-y-1.5">
          <h1 className="text-4xl leading-tight">{p.name}</h1>
          {p.title && <p className="text-lg text-ink-soft">{p.title}</p>}
          <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
            <span className="inline-flex items-center gap-1.5"><Building2 aria-hidden className="size-4" />{[department, p.university].filter(Boolean).join(', ') || 'University unknown'}</span>
            {p.email && <a href={`mailto:${p.email}`} className="ink-link inline-flex items-center gap-1.5"><Mail aria-hidden className="size-4" />{p.email}</a>}
            {p.faculty_url && <SourceLink url={p.faculty_url}>Official profile</SourceLink>}
            {p.openalex_id && <SourceLink url={`https://openalex.org/${p.openalex_id}`}>OpenAlex</SourceLink>}
            {p.orcid && <SourceLink url={p.orcid.startsWith('http') ? p.orcid : `https://orcid.org/${p.orcid}`}>ORCID</SourceLink>}
          </p>
        </div>
        {best && (
          <div className="flex flex-wrap gap-2">
            <Button asChild><Link to={`/opportunities/${best.id}`}>View opportunity <ArrowRight data-icon="inline-end" /></Link></Button>
            <Button variant="outline" asChild><Link to={`/drafts?for=${best.id}`}><FilePenLine />Draft email</Link></Button>
          </div>
        )}
      </header>

      <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(280px,1fr)]">
        <div className="space-y-6">
          <Section id="overview" title="Research overview" icon={Microscope}>
            {topics.length === 0 ? <p className="text-muted-foreground">No research summary yet.</p> : (
              <ul className="flex flex-wrap gap-2">{topics.map((t) => <li key={t} className="rounded-md border border-border bg-well px-2.5 py-1 text-sm text-foreground">{t}</li>)}</ul>
            )}
          </Section>
          <Publications pubs={p.publications} relevant={relevant} />
          <Section id="signals" title="Funding and recruitment signals" icon={Megaphone}>
            <Signals prof={p} opps={mine} />
          </Section>
        </div>

        <div className="space-y-6 lg:sticky lg:top-6">
          <Section id="activity" title="Research activity" icon={BookOpen}><Activity pubs={p.publications} /></Section>
          <Section id="fit" title="Research fit" icon={Sparkles}>
            {matches.length === 0 ? <p className="text-sm text-muted-foreground">Not compared with your interests yet. Evaluate this professor’s programs from the Researchers page.</p> : (
              <ul className="space-y-2.5">
                {[...new Map(matches.map((m) => [m.interest, m])).values()].map((m) => (
                  <li key={m.interest} className="text-sm">
                    <p className="font-medium text-foreground">{m.interest}</p>
                    <p className="text-muted-foreground">via “{m.paper}”</p>
                  </li>
                ))}
              </ul>
            )}
          </Section>
          <Section id="evidence" title="Evidence" icon={FileSearch}><SourceList claims={claims} /></Section>
        </div>
      </div>
    </div>
  )
}
