import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, ChevronDown, Compass, Link2, Loader2, Microscope, Scale, Search } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import { Pill } from '@/components/app/pills'
import { RowsSkeleton } from '@/components/app/states'
import { TagInput } from '@/components/app/tags'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { api, type Degree, type Job } from '@/lib/api'
import { countryList, DEGREE, REGIONS, timeAgo } from '@/lib/format'
import { cn } from '@/lib/utils'

// The research pipeline behind the Researchers page: add researchers, evaluate their programs, watch the jobs.

const useJobs = () => useQuery({
  queryKey: ['jobs'], queryFn: api.jobs,
  refetchInterval: (q) => (q.state.data?.some((j) => j.status === 'running' || j.status === 'queued') ? 3000 : false),
})
const toggle = <T,>(list: T[], v: T) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v])

function useStarted() {
  const qc = useQueryClient()
  return (msg: string) => {
    qc.invalidateQueries({ queryKey: ['jobs'] })
    toast.success(msg, { description: 'Progress appears under Recent activity. You can leave this page.' })
  }
}

/** Discover → Verify → Shortlist, each with where it stands now. */
export function PipelineSteps() {
  const profs = useQuery({ queryKey: ['professors', 'directory'], queryFn: () => api.professors(200) })
  const opps = useQuery({ queryKey: ['opportunities'], queryFn: () => api.opportunities(true) })
  const apps = useQuery({ queryKey: ['applications'], queryFn: api.applications })
  const jobs = useJobs()
  const lastEval = jobs.data?.find((j) => j.job_type === 'evaluation' && j.status === 'completed')
  const evalRunning = jobs.data?.some((j) => j.job_type === 'evaluation' && (j.status === 'running' || j.status === 'queued'))
  const steps = [
    { n: 1, title: 'Discover', detail: profs.data ? `${profs.data.length} researchers found` : 'Find relevant researchers', href: '#add', done: !!profs.data?.length },
    { n: 2, title: 'Verify', detail: evalRunning ? 'Checking programs now…' : lastEval ? `${opps.data?.length ?? '…'} opportunities · ${timeAgo(lastEval.completed_at ?? lastEval.created_at)}` : 'Check funding and deadlines', href: '#evaluate', done: !!lastEval },
    { n: 3, title: 'Shortlist', detail: `${(apps.data ?? []).filter((a) => a.status === 'shortlisted').length} saved`, href: '/shortlist', done: (apps.data ?? []).some((a) => a.status === 'shortlisted') },
  ]
  return (
    <ol aria-label="Research steps" className="grid gap-3 sm:grid-cols-3">
      {steps.map((s) => {
        const inner = (
          <>
            <span aria-hidden className={cn('grid size-8 shrink-0 place-items-center rounded-full text-sm font-semibold', s.done ? 'bg-navy text-navy-ink' : 'border border-input bg-sheet text-muted-foreground')}>
              {s.done ? <Check className="size-4" /> : s.n}
            </span>
            <span className="min-w-0">
              <span className="block font-heading text-base font-semibold text-foreground">{s.title}</span>
              <span className="block truncate text-sm text-muted-foreground">{s.detail}</span>
            </span>
          </>
        )
        const cls = 'flex items-center gap-3 rounded-xl border border-border bg-sheet px-4 py-3 transition-colors hover:border-input focus-visible:outline-2 focus-visible:outline-ring'
        return <li key={s.n}>{s.href.startsWith('#') ? <a href={s.href} className={cls}>{inner}</a> : <Link to={s.href} className={cls}>{inner}</Link>}</li>
      })}
    </ol>
  )
}

/** Countries by region; the region checkbox selects or clears all of its countries. */
function CountryPicker({ value, onChange }: { value: string[]; onChange: (v: string[]) => void }) {
  return (
    <fieldset className="space-y-2">
      <legend className="text-sm font-medium">Countries <span className="font-normal text-muted-foreground">({value.length} selected)</span></legend>
      {Object.entries(REGIONS).map(([region, names]) => {
        const codes = Object.keys(names)
        const picked = codes.filter((c) => value.includes(c)).length
        return (
          <div key={region} className="flex flex-col gap-2 sm:flex-row sm:items-start sm:gap-4">
            <label className="flex w-36 shrink-0 items-center gap-2 pt-1 text-sm">
              <Checkbox checked={picked === codes.length ? true : picked ? 'indeterminate' : false}
                onCheckedChange={() => onChange(picked === codes.length ? value.filter((c) => !codes.includes(c)) : [...new Set([...value, ...codes])])} />
              {region}
            </label>
            <div className="flex flex-wrap gap-1.5">
              {codes.map((c) => (
                <button key={c} type="button" aria-pressed={value.includes(c)} onClick={() => onChange(toggle(value, c))}
                  className={cn('rounded-lg border px-2.5 py-1 text-sm transition-colors focus-visible:outline-2 focus-visible:outline-ring',
                    value.includes(c) ? 'border-navy bg-navy text-navy-ink' : 'border-border bg-sheet text-muted-foreground hover:border-input hover:text-foreground')}>
                  {names[c]}
                </button>
              ))}
            </div>
          </div>
        )
      })}
    </fieldset>
  )
}

function ByArea() {
  const profile = useQuery({ queryKey: ['profile'], queryFn: api.profile, retry: false })
  const [edited, setAreas] = useState<string[] | null>(null)
  const areas = edited ?? profile.data?.research_interests ?? []  // your profile's interests until you edit them
  const [countries, setCountries] = useState<string[]>(['US', 'CA'])
  const [max, setMax] = useState(20)
  const [findPages, setFindPages] = useState(true)
  const [refresh, setRefresh] = useState(false)
  const started = useStarted()
  const discover = useMutation({
    mutationFn: () => api.startDiscovery({ research_areas: areas, countries, max_results: max, find_pages: findPages, refresh }),
    onSuccess: () => started('Discovery started'),
    onError: (e) => toast.error('Couldn’t start discovery', { description: e.message }),
  })
  return (
    <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); discover.mutate() }}>
      <div className="space-y-1.5">
        <Label htmlFor="areas">Research areas</Label>
        <TagInput id="areas" value={areas} onChange={setAreas} placeholder="Add an area and press Enter" />
        <p className="text-xs text-muted-foreground">Searches OpenAlex for researchers actively publishing in these areas, then verifies their faculty pages.</p>
      </div>
      <CountryPicker value={countries} onChange={setCountries} />
      <div className="flex flex-wrap items-end gap-x-6 gap-y-3">
        <div className="w-32 space-y-1.5">
          <Label htmlFor="max">Max researchers</Label>
          <Input id="max" type="number" min={1} max={100} value={max} onChange={(e) => setMax(Math.min(100, Math.max(1, Number(e.target.value) || 1)))} />
        </div>
        <label className="flex h-9 items-center gap-2 text-sm"><Checkbox checked={findPages} onCheckedChange={(c) => setFindPages(!!c)} />Verify faculty pages</label>
        <label className="flex h-9 items-center gap-2 text-sm" title="Off: researchers already in your list are skipped, so the max counts only new ones">
          <Checkbox checked={refresh} onCheckedChange={(c) => setRefresh(!!c)} />Include ones I already have (refresh their papers)
        </label>
        <Button type="submit" className="ml-auto" disabled={discover.isPending || areas.length === 0 || countries.length === 0}>
          {discover.isPending ? <Loader2 className="animate-spin" /> : <Compass />}Start discovery
        </Button>
      </div>
    </form>
  )
}

function SpecificProfessor() {
  const qc = useQueryClient()
  const [url, setUrl] = useState('')
  const [text, setText] = useState('')
  const [mode, setMode] = useState<'url' | 'post'>('url')
  const add = useMutation({
    mutationFn: async () => {
      const src = await api.ingest(mode === 'url' ? { url } : { text, url: url || null, source_type: 'social_post' })
      return api.extract(src.source_id)
    },
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ['professors'] })
      setUrl(''); setText('')
      if (r.professor_id) toast.success('Professor saved', { description: `${r.verified_fields} facts verified against the page. Evaluate programs to rank them.` })
      else toast.info(mode === 'post' ? 'Saved as an unverified lead' : 'Page saved, no professor found', { description: mode === 'post' ? 'Posts are never trusted directly. Add the professor’s faculty page to verify.' : r.warnings[0] })
    },
    onError: (e) => toast.error('Couldn’t add this', { description: e.message }),
  })
  const ready = mode === 'url' ? /^https?:\/\/\S+\.\S+/.test(url) : text.trim().length > 20
  return (
    <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); if (ready) add.mutate() }}>
      <div role="group" aria-label="Source" className="inline-flex rounded-lg bg-well p-0.5 text-sm">
        {([['url', 'Faculty page URL'], ['post', 'Pasted post']] as const).map(([m, label]) => (
          <button key={m} type="button" aria-pressed={mode === m} onClick={() => setMode(m)}
            className={cn('rounded-md px-2.5 py-1 font-medium', mode === m ? 'bg-sheet text-foreground shadow-xs' : 'text-muted-foreground hover:text-foreground')}>{label}</button>
        ))}
      </div>
      {mode === 'url' ? (
        <div className="space-y-1.5">
          <Label htmlFor="lead-url">Faculty page URL</Label>
          <Input id="lead-url" type="url" inputMode="url" placeholder="https://www.cs.university.edu/people/name" value={url} onChange={(e) => setUrl(e.target.value)} />
          <p className="text-xs text-muted-foreground">One professor’s official page. Every fact is checked word for word against it before it’s saved.</p>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-[1fr_16rem]">
          <div className="space-y-1.5"><Label htmlFor="lead-text">Post text</Label><Textarea id="lead-text" rows={3} value={text} onChange={(e) => setText(e.target.value)} placeholder="Paste the post, e.g. “Fully funded PhD positions in quantum ML at …”" /></div>
          <div className="space-y-1.5"><Label htmlFor="lead-src">Link to the post (optional)</Label><Input id="lead-src" type="url" value={url} onChange={(e) => setUrl(e.target.value)} /></div>
        </div>
      )}
      <Button type="submit" disabled={!ready || add.isPending}>{add.isPending ? <><Loader2 className="animate-spin" />Reading page…</> : <><Link2 />Add professor</>}</Button>
    </form>
  )
}

/** Step 1: two ways in, by research area or one specific professor. */
export function AddResearchersPanel() {
  return (
    <section id="add" aria-labelledby="add-title" className="sheet scroll-mt-6 p-5 sm:p-6">
      <h2 id="add-title" className="flex items-center gap-2 text-xl"><Microscope aria-hidden className="size-5 text-signal" />Add researchers</h2>
      <Tabs defaultValue="area" className="mt-3 gap-4">
        <TabsList><TabsTrigger value="area"><Search aria-hidden />By research area</TabsTrigger><TabsTrigger value="one"><Link2 aria-hidden />Specific professor</TabsTrigger></TabsList>
        <TabsContent value="area"><ByArea /></TabsContent>
        <TabsContent value="one"><SpecificProfessor /></TabsContent>
      </Tabs>
    </section>
  )
}

/** Step 2: verify programs and rank, the job that turns researchers into opportunities. */
export function EvaluatePanel() {
  const profs = useQuery({ queryKey: ['professors', 'directory'], queryFn: () => api.professors(200) })
  const jobs = useJobs()
  const [degrees, setDegrees] = useState<Degree[]>(['phd', 'thesis_masters'])
  const [force, setForce] = useState(false)
  const started = useStarted()
  const evaluate = useMutation({
    mutationFn: () => api.evaluate({ degree_types: degrees, force }),
    onSuccess: () => started('Evaluation started'),
    onError: (e) => toast.error('Couldn’t start evaluation', { description: e.message }),
  })
  const lastEval = jobs.data?.find((j) => j.job_type === 'evaluation' && j.status === 'completed')
  const running = jobs.data?.some((j) => j.job_type === 'evaluation' && (j.status === 'running' || j.status === 'queued'))
  const known = profs.data?.filter((p) => p.university).length
  return (
    <section id="evaluate" aria-labelledby="evaluate-title" className="sheet flex scroll-mt-6 flex-col gap-4 p-5 sm:p-6">
      <div>
        <h2 id="evaluate-title" className="flex items-center gap-2 text-xl"><Scale aria-hidden className="size-5 text-signal" />Evaluate programs</h2>
        <p className="mt-1 text-sm text-muted-foreground">Finds official program pages, funding, deadlines and requirements for each researcher, then ranks them.</p>
      </div>
      <fieldset className="space-y-1.5">
        <legend className="text-sm font-medium">Degrees</legend>
        <div className="flex flex-wrap gap-x-4 gap-y-2">
          {(Object.keys(DEGREE) as Degree[]).map((d) => (
            <label key={d} className="flex items-center gap-2 text-sm"><Checkbox checked={degrees.includes(d)} onCheckedChange={() => setDegrees(toggle(degrees, d))} />{DEGREE[d]}</label>
          ))}
        </div>
      </fieldset>
      <label className="flex items-start gap-2 text-sm">
        <Checkbox checked={force} onCheckedChange={(c) => setForce(!!c)} className="mt-0.5" />
        <span>Re-check everything<span className="block text-xs text-muted-foreground">Programs checked in the last 30 days are normally reused. Turn on to pick up new deadlines.</span></span>
      </label>
      <p className="rounded-lg bg-well px-3 py-2 text-xs text-muted-foreground">
        {known ?? '…'} researchers × {degrees.length} degrees · about 15 to 20 minutes for a full re-check
        <br />{running ? 'An evaluation is running now.' : lastEval ? `Last run ${timeAgo(lastEval.completed_at ?? lastEval.created_at)}.` : 'Not run yet.'}
      </p>
      <Button className="mt-auto w-full" onClick={() => evaluate.mutate()} disabled={evaluate.isPending || running || degrees.length === 0}>
        {evaluate.isPending || running ? <Loader2 className="animate-spin" /> : <Scale />}{running ? 'Evaluating…' : 'Evaluate programs'}
      </Button>
    </section>
  )
}

const STATUS = {
  completed: { label: 'Completed', tone: 'success' }, failed: { label: 'Failed', tone: 'danger' },
  running: { label: 'Running', tone: 'info' }, queued: { label: 'Queued', tone: 'neutral' },
} as const

function JobRow({ job, expanded, onToggle }: { job: Job; expanded: boolean; onToggle: () => void }) {
  const live = job.status === 'running' || job.status === 'queued'
  const events = useQuery({ queryKey: ['job-events', job.id], queryFn: () => api.jobEvents(job.id), enabled: expanded || live, refetchInterval: live ? 3000 : false })
  const programEvents = (events.data ?? []).filter((e) => e.event_type === 'program').length
  const total = Number((job.input.professor_ids as string[] | undefined)?.length ?? 0) * Number((job.input.degree_types as string[] | undefined)?.length ?? 2)
  const pct = live && job.job_type === 'evaluation' && total > 0 ? Math.min(100, Math.round((programEvents / total) * 100)) : null
  const isEval = job.job_type === 'evaluation'
  const label = isEval ? 'Evaluate programs' : `Discover: ${((job.input.research_areas as string[] | undefined)?.join(', ') || (job.input.query as string) || 'researchers').replace(/_/g, ' ')}`
  const detail = isEval
    ? `${(job.input.degree_types as string[] | undefined)?.map((d) => DEGREE[d as Degree] ?? d).join(', ') ?? ''}`
    : `${countryList((job.input.countries as string[] | undefined) ?? [])} · up to ${job.input.max_results ?? '?'}`
  const st = STATUS[job.status as keyof typeof STATUS] ?? { label: job.status, tone: 'neutral' as const }
  return (
    <li>
      <button type="button" onClick={onToggle} aria-expanded={expanded}
        className="grid w-full grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1 px-4 py-3 text-left hover:bg-well/60 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring sm:grid-cols-[auto_minmax(0,1fr)_9rem_auto_7rem]">
        <span aria-hidden className="grid size-9 place-items-center rounded-full bg-accent-soft text-signal">{isEval ? <Scale className="size-4" /> : <Search className="size-4" />}</span>
        <span className="min-w-0">
          <span className="block truncate font-medium text-foreground">{label}</span>
          <span className="block truncate text-xs text-muted-foreground">{detail}{job.cost_usd ? ` · $${job.cost_usd.toFixed(2)}` : ''}</span>
        </span>
        <span className="hidden sm:block">
          {pct !== null && <span className="flex items-center gap-2"><span className="h-1.5 flex-1 overflow-hidden rounded-full bg-well-2"><span className="block h-full rounded-full bg-signal" style={{ width: `${pct}%` }} /></span><span className="num text-xs text-muted-foreground">{pct}%</span></span>}
        </span>
        <Pill tone={st.tone}>{st.label}</Pill>
        <span className="col-span-3 flex items-center justify-end gap-1 text-xs text-muted-foreground sm:col-span-1">
          {timeAgo(job.completed_at ?? job.created_at)}<ChevronDown aria-hidden className={cn('size-4 transition-transform', expanded && 'rotate-180')} />
        </span>
      </button>
      {expanded && (
        <div className="border-t border-border bg-well/40 px-4 py-3">
          {job.error_message && <p className="mb-2 text-sm text-error">{job.error_message}</p>}
          <ol className="max-h-64 space-y-1 overflow-y-auto font-mono text-xs" aria-live={live ? 'polite' : 'off'}>
            {(events.data ?? []).map((e) => (
              <li key={e.id} className="flex gap-2"><span className="num shrink-0 text-muted-foreground">{new Date(e.created_at).toLocaleTimeString()}</span><span className="text-ink-soft">{e.message}</span></li>
            ))}
            {events.isLoading && <li className="text-muted-foreground">Loading…</li>}
          </ol>
        </div>
      )}
    </li>
  )
}

export function ActivityPanel() {
  const jobs = useJobs()
  const [expanded, setExpanded] = useState<string | null>(null)
  const [all, setAll] = useState(false)
  const list = jobs.data ?? []
  return (
    <section aria-labelledby="activity-title" className="sheet overflow-hidden">
      <div className="flex items-baseline justify-between gap-4 px-5 pt-5 pb-3 sm:px-6">
        <h2 id="activity-title" className="text-xl">Recent activity</h2>
        {list.length > 4 && <button type="button" onClick={() => setAll(!all)} className="ink-link text-sm">{all ? 'Show fewer' : `View all ${list.length}`}</button>}
      </div>
      {jobs.isLoading ? <div className="px-5 pb-5"><RowsSkeleton rows={3} /></div> : list.length === 0 ? (
        <p className="px-5 pb-5 text-sm text-muted-foreground sm:px-6">No jobs yet. Start a discovery above.</p>
      ) : (
        <ul className="divide-y divide-border border-t border-border">
          {list.slice(0, all ? 20 : 4).map((j) => <JobRow key={j.id} job={j} expanded={expanded === j.id} onToggle={() => setExpanded(expanded === j.id ? null : j.id)} />)}
        </ul>
      )}
    </section>
  )
}
