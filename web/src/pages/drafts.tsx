import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BookOpen, Check, Copy, FileText, Loader2, Mail, PenLine, Quote, Search, Send, Sparkles, TriangleAlert } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import { DeadlineChip, Pill, ScoreBadge } from '@/components/app/pills'
import { EmptyState, ErrorState, PageHeader, RowsSkeleton } from '@/components/app/states'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { api, CLOSED, type Draft, type Opportunity } from '@/lib/api'
import { DEGREE, funding, STATUS_LABEL, timeAgo } from '@/lib/format'
import { cn } from '@/lib/utils'

function Picker({ selected, onSelect }: { selected: string | null; onSelect: (id: string) => void }) {
  const opps = useQuery({ queryKey: ['opportunities'], queryFn: () => api.opportunities(true) })
  const apps = useQuery({ queryKey: ['applications'], queryFn: api.applications })
  const [text, setText] = useState('')
  const tracked = new Map((apps.data ?? []).filter((a) => !CLOSED.includes(a.status)).map((a) => [a.opportunity_id, a]))
  const list = (opps.data ?? []).filter((o) => tracked.has(o.id) || (!o.excluded_reason && o.overall_score >= 45))
    .filter((o) => !text || `${o.professor} ${o.university}`.toLowerCase().includes(text.toLowerCase()))
    .sort((a, b) => Number(tracked.has(b.id)) - Number(tracked.has(a.id)) || b.overall_score - a.overall_score)
  return (
    <div className="flex flex-col gap-3">
      <div className="relative">
        <Search aria-hidden className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input aria-label="Filter professors" placeholder="Filter" className="pl-8" value={text} onChange={(e) => setText(e.target.value)} />
      </div>
      {opps.isLoading ? <RowsSkeleton rows={6} /> : (
        <ul className="flex max-h-[70vh] flex-col gap-1 overflow-y-auto pr-1" aria-label="Opportunities">
          {list.map((o) => {
            const app = tracked.get(o.id)
            return (
              <li key={o.id}>
                <button onClick={() => onSelect(o.id)} aria-current={selected === o.id}
                  className={cn('flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left transition-colors duration-150 focus-visible:outline-2 focus-visible:outline-ring',
                    selected === o.id ? 'bg-accent text-accent-foreground' : 'hover:bg-muted')}>
                  <ScoreBadge score={o.overall_score} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium">{o.professor}</span>
                    <span className="block truncate text-xs text-muted-foreground">{o.university.replace('University of ', 'U ')} · {DEGREE[o.degree_type]}</span>
                  </span>
                  {app && <span className="shrink-0 rounded bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium text-primary">{STATUS_LABEL[app.status]}</span>}
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}

function Editor({ opp, kind }: { opp: Opportunity; kind: Draft['kind'] }) {
  const qc = useQueryClient()
  const drafts = useQuery({ queryKey: ['drafts', opp.id], queryFn: () => api.drafts(opp.id) })
  const apps = useQuery({ queryKey: ['applications'], queryFn: api.applications })
  const versions = (drafts.data ?? []).filter((d) => d.kind === kind)
  const [versionId, setVersionId] = useState<string | null>(null)
  const current = versions.find((d) => d.id === versionId) ?? versions[0]
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [copied, setCopied] = useState(false)
  useEffect(() => { setSubject(current?.subject ?? ''); setBody(current?.body ?? '') }, [current?.id]) // eslint-disable-line react-hooks/exhaustive-deps
  const dirty = !!current && (body !== current.body || (kind === 'email' && subject !== (current.subject ?? '')))

  const generate = useMutation({
    mutationFn: () => api.createDraft(opp.id, kind),
    onSuccess: (d) => { qc.invalidateQueries({ queryKey: ['drafts', opp.id] }); setVersionId(d.id); toast.success(kind === 'email' ? 'Email drafted' : 'SOP outline drafted') },
    onError: (e) => toast.error('Couldn’t write a draft', { description: e.message }),
  })
  const save = useMutation({
    mutationFn: () => api.updateDraft(current!.id, kind === 'email' ? { subject, body } : { body }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['drafts', opp.id] }); toast.success('Saved') },
    onError: (e) => toast.error('Couldn’t save', { description: e.message }),
  })
  const markContacted = useMutation({
    mutationFn: async () => {
      const app = apps.data?.find((a) => a.opportunity_id === opp.id) ?? await api.track(opp.id)
      return api.updateApplication(app.id, { status: 'contacted' })
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['applications'] }); toast.success('Marked as contacted', { description: 'Follow-up reminder set for 10 days.' }) },
  })
  const app = apps.data?.find((a) => a.opportunity_id === opp.id)
  const canMarkSent = !app || app.status === 'shortlisted' || app.status === 'researching'
  const leave = (fn: () => void) => { if (!dirty || confirm('Discard your unsaved edits to this draft?')) fn() }
  const words = body.trim() ? body.trim().split(/\s+/).length : 0
  const copy = async () => {
    await navigator.clipboard.writeText(kind === 'email' ? `Subject: ${subject}\n\n${body}` : body)
    setCopied(true); setTimeout(() => setCopied(false), 1500)
  }
  const mailto = `mailto:${app?.professor_email ?? ''}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`

  if (drafts.isLoading) return <RowsSkeleton rows={6} />
  if (!current) {
    return (
      <EmptyState icon={kind === 'email' ? Mail : FileText} title={kind === 'email' ? 'No email yet' : 'No SOP outline yet'}
        action={<Button onClick={() => generate.mutate()} disabled={generate.isPending}>{generate.isPending ? <Loader2 className="animate-spin" /> : <Sparkles />}{generate.isPending ? 'Writing… (about 10 s)' : kind === 'email' ? 'Draft email' : 'Draft SOP outline'}</Button>}>
        Written from your profile, {opp.professor}’s stored papers and the verified program facts. Nothing is sent.
      </EmptyState>
    )
  }
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Versions">
          {versions.map((d, i) => (
            <button key={d.id} onClick={() => leave(() => setVersionId(d.id))} aria-pressed={d.id === current.id}
              className={cn('min-h-8 rounded-md border px-2.5 text-xs transition-colors focus-visible:outline-2 focus-visible:outline-ring', d.id === current.id ? 'border-primary bg-accent text-accent-foreground' : 'hover:bg-muted')}>
              v{versions.length - i} · {timeAgo(d.created_at)}
            </button>
          ))}
        </div>
        <Button variant="outline" size="sm" onClick={() => leave(() => generate.mutate())} disabled={generate.isPending}>
          {generate.isPending ? <Loader2 className="animate-spin" /> : <Sparkles />}{generate.isPending ? 'Writing…' : 'New version'}
        </Button>
      </div>

      {current.warnings.length > 0 && (
        <ul className="space-y-1.5" aria-label="Warnings">
          {current.warnings.map((w) => (
            <li key={w} className="flex gap-2 rounded-lg border border-warning/40 bg-warning/10 px-3 py-2 text-sm"><TriangleAlert aria-hidden className="mt-0.5 size-4 shrink-0 text-warning" />{w}</li>
          ))}
        </ul>
      )}

      {kind === 'email' && (
        <div className="space-y-1.5">
          <Label htmlFor="subject">Subject</Label>
          <Input id="subject" value={subject} onChange={(e) => setSubject(e.target.value)} />
        </div>
      )}
      <div className="space-y-1.5">
        <div className="flex items-baseline justify-between">
          <Label htmlFor="body">{kind === 'email' ? 'Message' : 'Outline (Markdown)'}</Label>
          <span className={cn('text-xs tabular', kind === 'email' && words > 200 ? 'font-medium text-warning-foreground dark:text-warning' : 'text-muted-foreground')}>
            {words} words{kind === 'email' && ' · aim for under 180'}
          </span>
        </div>
        <Textarea id="body" value={body} onChange={(e) => setBody(e.target.value)} className={cn('min-h-80 leading-relaxed', kind === 'sop_outline' && 'font-mono text-[13px]')} />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Button onClick={() => save.mutate()} disabled={!dirty || save.isPending}>{save.isPending ? 'Saving…' : dirty ? 'Save changes' : 'Saved'}</Button>
        <Button variant="outline" onClick={copy}>{copied ? <Check /> : <Copy />}{copied ? 'Copied' : 'Copy'}</Button>
        {kind === 'email' && (
          <>
            <Button variant="outline" asChild><a href={mailto}><Send aria-hidden />Open in mail app</a></Button>
            {canMarkSent ? (
              <Button variant="ghost" onClick={() => markContacted.mutate()} disabled={markContacted.isPending}><Check aria-hidden />I sent it</Button>
            ) : (
              <span className="inline-flex items-center gap-1.5 px-2 text-sm text-muted-foreground"><Check aria-hidden className="size-4" />{STATUS_LABEL[app!.status]}</span>
            )}
          </>
        )}
      </div>
      {current.sources.publication_ids && (
        <p className="text-xs text-muted-foreground">
          Built from your profile{current.sources.profile_updated_at ? ` as saved ${new Date(current.sources.profile_updated_at).toLocaleDateString()}` : ''},
          {' '}{current.sources.publication_ids.length} of their papers and {current.sources.program_source_ids?.length ?? 0} official program pages
          {' '}· {current.model} · {current.prompt_version}
        </p>
      )}
      <p className="text-xs text-muted-foreground">Drafts are never sent for you. Check the facts, add one specific detail of your own, then send it from your email.</p>
    </div>
  )
}

function Context({ opp, cited }: { opp: Opportunity; cited: Set<string> }) {
  const prof = useQuery({ queryKey: ['professor', opp.professor_id], queryFn: () => api.professor(opp.professor_id) })
  const f = funding(opp.funding_status)
  const matched = new Set((opp.explanation.research_matches ?? []).map((m) => m.publication_id))
  const papers = useMemo(() => [...(prof.data?.publications ?? [])].sort((a, b) =>
    Number(cited.has(b.id)) - Number(cited.has(a.id)) || Number(matched.has(b.id)) - Number(matched.has(a.id))
    || (b.publication_year ?? 0) - (a.publication_year ?? 0)), [prof.data, cited]) // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className="space-y-4">
      <Card className="gap-3 py-4">
        <CardHeader className="px-4"><CardTitle className="font-sans text-sm">Program</CardTitle></CardHeader>
        <CardContent className="space-y-2 px-4 text-sm">
          <p className="font-medium">{opp.program}</p>
          <div className="flex flex-wrap gap-2"><Pill tone={f.tone} title={f.hint}>{f.label}</Pill><DeadlineChip date={opp.deadline} compact /></div>
          {prof.data?.research_summary && <p className="text-muted-foreground">{prof.data.research_summary}</p>}
        </CardContent>
      </Card>
      <Card className="gap-3 py-4">
        <CardHeader className="px-4"><CardTitle className="flex items-center gap-2 font-sans text-sm"><BookOpen aria-hidden className="size-4" />Papers <span className="font-normal text-muted-foreground tabular">{papers.length}</span></CardTitle></CardHeader>
        <CardContent className="px-4">
          {prof.isLoading ? <RowsSkeleton rows={3} /> : (
            <ul className="max-h-[55vh] space-y-2 overflow-y-auto pr-1">
              {papers.map((p) => (
                <li key={p.id} className={cn('rounded-lg border p-2.5 text-sm', cited.has(p.id) && 'border-primary/50 bg-accent/50')}>
                  <div className="mb-1 flex flex-wrap gap-1.5">
                    {cited.has(p.id) && <Pill tone="info">Cited in draft</Pill>}
                    {matched.has(p.id) && <Pill tone="success">Matches your interests</Pill>}
                  </div>
                  <a href={p.url ?? p.open_access_url ?? '#'} target="_blank" rel="noreferrer" className="font-medium leading-snug underline-offset-2 hover:underline">{p.title}</a>
                  <p className="text-xs text-muted-foreground">{p.publication_year}{p.author_position ? ` · ${p.author_position} author` : ''}</p>
                  {p.abstract && (
                    <details className="mt-1">
                      <summary className="cursor-pointer text-xs text-muted-foreground">Abstract</summary>
                      <p className="mt-1 flex gap-1.5 text-xs leading-relaxed text-muted-foreground"><Quote aria-hidden className="size-3 shrink-0" />{p.abstract}</p>
                    </details>
                  )}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

export function DraftsPage() {
  const [params, setParams] = useSearchParams()
  const selected = params.get('for')
  const kind = (params.get('kind') as Draft['kind']) ?? 'email'
  const opps = useQuery({ queryKey: ['opportunities'], queryFn: () => api.opportunities(true) })
  const drafts = useQuery({ queryKey: ['drafts', selected], queryFn: () => api.drafts(selected!), enabled: !!selected })
  const opp = opps.data?.find((o) => o.id === selected)
  const cited = new Set((drafts.data ?? []).filter((d) => d.kind === kind).slice(0, 1).flatMap((d) => d.cited_publication_ids))
  const setParam = (k: string, v: string) => setParams((p) => { p.set(k, v); return p })

  return (
    <div className="space-y-6">
      <PageHeader title="Writing Studio" description="Emails to professors and statement-of-purpose outlines, grounded in their papers and your profile." />
      {opps.isError && <ErrorState error={opps.error} retry={() => opps.refetch()} />}
      <div className="grid gap-6 lg:grid-cols-[16rem_1fr] xl:grid-cols-[16rem_1fr_20rem]">
        <aside aria-label="Choose an opportunity"><Picker selected={selected} onSelect={(id) => setParam('for', id)} /></aside>
        <section aria-label="Editor" className="min-w-0">
          {!opp ? (
            <EmptyState icon={PenLine} title="Pick a professor">Choose someone on the left. Tracked opportunities are listed first.</EmptyState>
          ) : (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="text-2xl font-semibold">{opp.professor}</h2>
                  <p className="text-sm text-muted-foreground">{opp.university} · {DEGREE[opp.degree_type]}</p>
                </div>
                <Tabs value={kind} onValueChange={(v) => setParam('kind', v)}>
                  <TabsList><TabsTrigger value="email"><Mail aria-hidden />Email</TabsTrigger><TabsTrigger value="sop_outline"><FileText aria-hidden />SOP outline</TabsTrigger></TabsList>
                </Tabs>
              </div>
              <Editor key={`${opp.id}-${kind}`} opp={opp} kind={kind} />
            </div>
          )}
        </section>
        {opp && <aside aria-label="Context" className="lg:col-span-2 xl:col-span-1"><Context opp={opp} cited={cited} /></aside>}
      </div>
    </div>
  )
}
