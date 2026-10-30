import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, CircleDashed, Compass, ExternalLink, Link2, Loader2, Scale, XCircle } from 'lucide-react'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { PageHeader, RowsSkeleton } from '@/components/app/states'
import { TagInput } from '@/components/app/tags'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Progress } from '@/components/ui/progress'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { api, type Degree, type Job } from '@/lib/api'
import { DEGREE, timeAgo } from '@/lib/format'
import { cn } from '@/lib/utils'

const JOB_ICON = { completed: CheckCircle2, failed: XCircle, running: Loader2, queued: CircleDashed } as const

function JobRow({ job, expanded, onToggle }: { job: Job; expanded: boolean; onToggle: () => void }) {
  const live = job.status === 'running' || job.status === 'queued'
  const events = useQuery({ queryKey: ['job-events', job.id], queryFn: () => api.jobEvents(job.id), enabled: expanded || live, refetchInterval: live ? 3000 : false })
  const Icon = JOB_ICON[job.status as keyof typeof JOB_ICON] ?? CircleDashed
  const programEvents = (events.data ?? []).filter((e) => e.event_type === 'program').length
  const total = Number((job.input.professor_ids as string[] | undefined)?.length ?? 0) * Number((job.input.degree_types as string[] | undefined)?.length ?? 2)
  const label = job.job_type === 'evaluation' ? 'Evaluate programs' : `Discover: ${(job.input.research_areas as string[] | undefined)?.join(', ') || (job.input.query as string)?.replace(/_/g, ' ') || 'professors'}`
  return (
    <li className="rounded-lg border">
      <button onClick={onToggle} aria-expanded={expanded} className="flex w-full items-center gap-3 px-3 py-2.5 text-left hover:bg-muted/50">
        <Icon aria-hidden className={cn('size-4 shrink-0', job.status === 'completed' && 'text-success', job.status === 'failed' && 'text-destructive', job.status === 'running' && 'animate-spin text-primary', job.status === 'queued' && 'text-muted-foreground')} />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium">{label}</span>
          <span className="block text-xs text-muted-foreground">{job.status} · {timeAgo(job.created_at)}{job.tokens_used ? ` · ${job.tokens_used.toLocaleString()} tokens` : ''}{job.cost_usd ? ` · $${job.cost_usd.toFixed(2)}` : ''}</span>
        </span>
      </button>
      {live && job.job_type === 'evaluation' && total > 0 && <Progress value={(programEvents / total) * 100} className="mx-3 mb-2 h-1 w-auto" aria-label="Evaluation progress" />}
      {expanded && (
        <div className="border-t px-3 py-2">
          {job.error_message && <p className="mb-2 text-sm text-destructive">{job.error_message}</p>}
          <ol className="max-h-64 space-y-1 overflow-y-auto font-mono text-xs" aria-live={live ? 'polite' : 'off'}>
            {(events.data ?? []).map((e) => (
              <li key={e.id} className="flex gap-2"><span className="shrink-0 text-muted-foreground tabular">{new Date(e.created_at).toLocaleTimeString()}</span><span>{e.message}</span></li>
            ))}
          </ol>
        </div>
      )}
    </li>
  )
}

function AddLead() {
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
      if (r.professor_id) toast.success('Professor saved', { description: `${r.verified_fields} facts verified against the page. Run “Evaluate programs” to rank them.` })
      else toast.info(mode === 'post' ? 'Saved as an unverified lead' : 'Page saved, no professor found', { description: mode === 'post' ? 'Posts are never trusted directly. Add the professor’s faculty page to verify.' : r.warnings[0] })
    },
    onError: (e) => toast.error('Couldn’t add this', { description: e.message }),
  })
  const ready = mode === 'url' ? /^https?:\/\/\S+\.\S+/.test(url) : text.trim().length > 20
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 font-sans text-base"><Link2 aria-hidden className="size-4" />Add a lead</CardTitle>
        <CardDescription>Found a professor yourself, or a post in a LinkedIn or Facebook group? Add it here. Facts are checked against the page before they’re saved.</CardDescription>
      </CardHeader>
      <CardContent>
        <Tabs value={mode} onValueChange={(v) => setMode(v as 'url' | 'post')} className="gap-4">
          <TabsList><TabsTrigger value="url">Faculty page URL</TabsTrigger><TabsTrigger value="post">Pasted post</TabsTrigger></TabsList>
          <form className="flex flex-col gap-3 sm:flex-row sm:items-end" onSubmit={(e) => { e.preventDefault(); if (ready) add.mutate() }}>
            <div className="flex-1 space-y-3">
              <TabsContent value="url" className="space-y-1.5">
                <Label htmlFor="lead-url">Page URL</Label>
                <Input id="lead-url" type="url" inputMode="url" placeholder="https://www.cs.university.edu/people/name" value={url} onChange={(e) => setUrl(e.target.value)} />
              </TabsContent>
              <TabsContent value="post" className="space-y-3">
                <div className="space-y-1.5"><Label htmlFor="lead-text">Post text</Label><Textarea id="lead-text" rows={4} value={text} onChange={(e) => setText(e.target.value)} placeholder="Paste the post, e.g. “Fully funded PhD positions in quantum ML at …”" /></div>
                <div className="space-y-1.5"><Label htmlFor="lead-src">Link to the post (optional)</Label><Input id="lead-src" type="url" value={url} onChange={(e) => setUrl(e.target.value)} /></div>
              </TabsContent>
            </div>
            <Button type="submit" disabled={!ready || add.isPending}>{add.isPending ? <><Loader2 className="animate-spin" />Reading page…</> : 'Add'}</Button>
          </form>
        </Tabs>
      </CardContent>
    </Card>
  )
}

export function DiscoverPage() {
  const qc = useQueryClient()
  const profile = useQuery({ queryKey: ['profile'], queryFn: api.profile, retry: false })
  const jobs = useQuery({ queryKey: ['jobs'], queryFn: api.jobs, refetchInterval: (q) => (q.state.data?.some((j) => j.status === 'running' || j.status === 'queued') ? 3000 : false) })
  const profs = useQuery({ queryKey: ['professors'], queryFn: api.professors })
  const [areas, setAreas] = useState<string[]>([])
  const [countries, setCountries] = useState<('US' | 'CA')[]>(['US', 'CA'])
  const [max, setMax] = useState(20)
  const [findPages, setFindPages] = useState(true)
  const [degrees, setDegrees] = useState<Degree[]>(['phd', 'thesis_masters'])
  const [force, setForce] = useState(false)
  const [expanded, setExpanded] = useState<string | null>(null)
  useEffect(() => { if (profile.data && areas.length === 0) setAreas(profile.data.research_interests) }, [profile.data]) // eslint-disable-line react-hooks/exhaustive-deps

  const onStarted = (j: { id?: string; job_id?: string }, msg: string) => {
    qc.invalidateQueries({ queryKey: ['jobs'] }); setExpanded(j.id ?? j.job_id ?? null); toast.success(msg, { description: 'Progress appears under Recent jobs. You can leave this page.' })
  }
  const discover = useMutation({
    mutationFn: () => api.startDiscovery({ research_areas: areas, countries, max_results: max, find_pages: findPages }),
    onSuccess: (j) => onStarted(j, 'Discovery started'),
    onError: (e) => toast.error('Couldn’t start discovery', { description: e.message }),
  })
  const evaluate = useMutation({
    mutationFn: () => api.evaluate({ degree_types: degrees, force }),
    onSuccess: (j) => onStarted(j, 'Evaluation started'),
    onError: (e) => toast.error('Couldn’t start evaluation', { description: e.message }),
  })
  const toggle = <T,>(list: T[], v: T) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v])

  return (
    <div className="space-y-6">
      <PageHeader title="Discover" description="Find active professors from publication data, then check their programs for funding, deadlines and eligibility." />
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 font-sans text-base"><Compass aria-hidden className="size-4" />1 · Find professors</CardTitle>
            <CardDescription>Searches OpenAlex for researchers publishing in your areas, then verifies their faculty pages.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="areas">Research areas</Label>
              <TagInput id="areas" value={areas} onChange={setAreas} placeholder="Add an area and press Enter" />
            </div>
            <fieldset className="space-y-2">
              <legend className="text-sm font-medium">Countries</legend>
              <div className="flex gap-4">
                {(['US', 'CA'] as const).map((c) => (
                  <label key={c} className="flex items-center gap-2 text-sm"><Checkbox checked={countries.includes(c)} onCheckedChange={() => setCountries(toggle(countries, c))} />{c === 'US' ? 'USA' : 'Canada'}</label>
                ))}
              </div>
            </fieldset>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label htmlFor="max">Max professors</Label>
                <Input id="max" type="number" min={1} max={100} value={max} onChange={(e) => setMax(Math.min(100, Math.max(1, Number(e.target.value) || 1)))} />
              </div>
              <label className="flex items-end gap-2 pb-2 text-sm"><Checkbox checked={findPages} onCheckedChange={(c) => setFindPages(!!c)} />Verify faculty pages</label>
            </div>
            <Button className="w-full" onClick={() => discover.mutate()} disabled={discover.isPending || areas.length === 0 || countries.length === 0}>
              {discover.isPending ? <Loader2 className="animate-spin" /> : <Compass />}Start discovery
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 font-sans text-base"><Scale aria-hidden className="size-4" />2 · Evaluate programs</CardTitle>
            <CardDescription>For every professor with a known university: finds official program pages, funding, deadlines and requirements, then ranks them.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <fieldset className="space-y-2">
              <legend className="text-sm font-medium">Degrees</legend>
              <div className="flex flex-wrap gap-4">
                {(Object.keys(DEGREE) as Degree[]).map((d) => (
                  <label key={d} className="flex items-center gap-2 text-sm"><Checkbox checked={degrees.includes(d)} onCheckedChange={() => setDegrees(toggle(degrees, d))} />{DEGREE[d]}</label>
                ))}
              </div>
            </fieldset>
            <label className="flex items-start gap-2 text-sm">
              <Checkbox checked={force} onCheckedChange={(c) => setForce(!!c)} className="mt-0.5" />
              <span>Re-check everything<span className="block text-xs text-muted-foreground">Programs checked in the last 30 days are normally reused. Turn on to pick up new deadlines.</span></span>
            </label>
            <p className="rounded-md bg-muted px-3 py-2 text-xs text-muted-foreground">{profs.data?.filter((p) => p.university).length ?? '…'} professors × {degrees.length} degrees · roughly 15–20 minutes for a full re-check.</p>
            <Button className="w-full" variant="secondary" onClick={() => evaluate.mutate()} disabled={evaluate.isPending || degrees.length === 0}>
              {evaluate.isPending ? <Loader2 className="animate-spin" /> : <Scale />}Evaluate programs
            </Button>
          </CardContent>
        </Card>
      </div>

      <AddLead />

      <section aria-labelledby="jobs" className="space-y-3">
        <h2 id="jobs" className="text-xl font-semibold">Recent jobs</h2>
        {jobs.isLoading ? <RowsSkeleton rows={3} /> : (
          <ul className="space-y-2">
            {(jobs.data ?? []).slice(0, 8).map((j) => <JobRow key={j.id} job={j} expanded={expanded === j.id} onToggle={() => setExpanded(expanded === j.id ? null : j.id)} />)}
            {jobs.data?.length === 0 && <p className="text-sm text-muted-foreground">No jobs yet.</p>}
          </ul>
        )}
      </section>

      <section aria-labelledby="profs" className="space-y-3">
        <h2 id="profs" className="text-xl font-semibold">Professors <span className="font-sans text-base font-normal text-muted-foreground tabular">{profs.data?.length ?? ''}</span></h2>
        {profs.isLoading ? <RowsSkeleton rows={5} /> : (
          <div className="overflow-hidden rounded-xl border bg-card">
            <Table>
              <TableHeader><TableRow className="bg-muted/40 hover:bg-muted/40"><TableHead className="pl-4">Name</TableHead><TableHead>University</TableHead><TableHead className="hidden md:table-cell">Research</TableHead><TableHead className="pr-4 text-right">Faculty page</TableHead></TableRow></TableHeader>
              <TableBody>
                {(profs.data ?? []).map((p) => (
                  <TableRow key={p.id}>
                    <TableCell className="pl-4"><p className="font-medium">{p.name}</p>{p.title && <p className="max-w-56 truncate text-xs text-muted-foreground">{p.title}</p>}</TableCell>
                    <TableCell className="text-sm">{p.university ?? <span className="text-muted-foreground">Unknown</span>}</TableCell>
                    <TableCell className="hidden max-w-sm md:table-cell"><p className="line-clamp-2 text-xs text-muted-foreground">{p.research_summary ?? 'No summary yet'}</p></TableCell>
                    <TableCell className="pr-4 text-right">
                      {p.faculty_url ? <a href={p.faculty_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-sm text-primary hover:underline">Open<ExternalLink aria-hidden className="size-3.5" /></a> : <span className="text-xs text-muted-foreground">Not found</span>}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </section>
    </div>
  )
}
