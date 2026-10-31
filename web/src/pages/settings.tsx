import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, ArrowRight, Bot, Database, Download, KeyRound, Loader2, Monitor, Moon, Palette, PlugZap, RefreshCw, SlidersHorizontal, Sun } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import { PageHeader } from '@/components/app/states'
import { setTheme, useTheme, type ThemeChoice } from '@/components/app/theme'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { api, type EmbeddingProvider, type LlmProvider, type LlmSettings, type LlmSettingsIn } from '@/lib/api'
import { timeAgo } from '@/lib/format'
import { cn } from '@/lib/utils'

function Section({ id, title, description, icon: Icon, children }: { id: string; title: string; description: string; icon: typeof Palette; children: React.ReactNode }) {
  return (
    <section aria-labelledby={id} className="sheet grid gap-5 p-5 sm:p-6 md:grid-cols-[16rem_minmax(0,1fr)]">
      <div>
        <h2 id={id} className="flex items-center gap-2 font-sans text-base font-semibold"><Icon aria-hidden className="size-[18px] text-signal" />{title}</h2>
        <p className="mt-1 text-sm text-muted-foreground">{description}</p>
      </div>
      <div className="min-w-0">{children}</div>
    </section>
  )
}

const THEMES: { value: ThemeChoice; label: string; icon: typeof Sun }[] = [
  { value: 'light', label: 'Light', icon: Sun },
  { value: 'dark', label: 'Dark', icon: Moon },
  { value: 'system', label: 'Match system', icon: Monitor },
]

const SOURCES = [
  ['OpenAlex', 'Finds active researchers and their publications.'],
  ['Official university pages', 'Faculty profiles, admissions, funding and deadline pages. Every extracted fact keeps its quote.'],
  ['Your pasted leads', 'Posts and links you add. Never trusted until matched to an official page.'],
] as const

const selectClass = 'h-9 w-full rounded-lg border border-input bg-sheet px-3 text-sm text-foreground shadow-xs outline-none focus-visible:outline-2 focus-visible:outline-ring'

function KeyField({ info, value, onChange, onRemove }: { info: LlmSettings['providers'][number]; value: string; onChange: (v: string) => void; onRemove: () => void }) {
  const status = info.key_saved ? 'A key is saved. Type a new one to replace it.' : info.key_in_env ? 'Using the key from .env.' : 'No key yet.'
  return (
    <div className="space-y-1.5">
      <Label htmlFor={`key-${info.id}`}>{info.label} API key{info.id === 'openai_compatible' && <span className="font-normal text-muted-foreground"> (optional)</span>}</Label>
      <div className="flex gap-2">
        <Input id={`key-${info.id}`} type="password" autoComplete="off" value={value} onChange={(e) => onChange(e.target.value)} placeholder={info.key_saved ? '••••••••••••' : 'Paste key'} />
        {info.key_saved && <Button type="button" variant="outline" onClick={onRemove}>Remove</Button>}
      </div>
      <p className="text-xs text-muted-foreground">{status}</p>
    </div>
  )
}

/** Which model reads pages, searches the web, drafts emails and embeds research. Saved in the local database. */
function AiProvider() {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['llm-settings'], queryFn: api.llmSettings })
  const [draft, setDraft] = useState<LlmSettingsIn>({})
  const [keys, setKeys] = useState<Partial<Record<LlmProvider, string>>>({})
  const [test, setTest] = useState<{ chat: string; embeddings: string } | null>(null)
  const save = useMutation({
    mutationFn: (body: LlmSettingsIn) => api.saveLlmSettings(body),
    onSuccess: (d) => {
      qc.setQueryData(['llm-settings'], d)
      setDraft({}); setKeys({}); setTest(null)
      toast.success('AI provider saved', d.embeddings_reset ? { description: 'The embedding model changed, so research-fit scores need a fresh evaluation.', duration: 8000 } : undefined)
    },
    onError: (e) => toast.error('Couldn’t save', { description: e.message }),
  })
  const runTest = useMutation({ mutationFn: api.testLlm, onSuccess: setTest, onError: (e) => toast.error('Test failed', { description: e.message }) })
  if (!q.data) return q.isError ? <p className="text-sm text-error">{q.error.message}</p> : <Loader2 className="size-4 animate-spin text-muted-foreground" />

  const v = { ...q.data, ...draft }
  const info = (id: LlmProvider) => q.data.providers.find((p) => p.id === id)!
  const chat = info(v.provider!)
  const embed = info(v.embedding_provider!)
  const set = (patch: LlmSettingsIn) => setDraft({ ...draft, ...patch })
  const dirty = Object.keys(draft).length > 0 || Object.values(keys).some((k) => k)
  const keyProviders = [...new Set([v.provider!, v.embedding_provider!])]

  return (
    <form className="space-y-5" onSubmit={(e) => { e.preventDefault(); save.mutate({ ...draft, keys: Object.fromEntries(Object.entries(keys).filter(([, k]) => k)) }) }}>
      <fieldset>
        <legend className="text-sm font-medium">Provider</legend>
        <div className="mt-2 grid gap-2 sm:grid-cols-2">
          {q.data.providers.map((p) => (
            <button key={p.id} type="button" aria-pressed={v.provider === p.id}
              onClick={() => set({ provider: p.id, model: '', ...(p.embeddings && v.embedding_provider === v.provider ? { embedding_provider: p.id as EmbeddingProvider, embedding_model: '' } : {}) })}
              className={cn('rounded-lg border px-3.5 py-2.5 text-left text-sm transition-colors focus-visible:outline-2 focus-visible:outline-ring',
                v.provider === p.id ? 'border-signal bg-accent-soft' : 'border-border bg-sheet hover:border-input')}>
              <span className="block font-medium text-foreground">{p.label}</span>
              <span className="block text-xs text-muted-foreground">{[p.web_search ? 'Web search' : 'No web search', p.embeddings ? 'embeddings' : 'no embeddings'].join(' · ')}</span>
            </button>
          ))}
        </div>
      </fieldset>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="ai-model">Model</Label>
          <Input id="ai-model" value={v.model ?? ''} placeholder={chat.default_model} onChange={(e) => set({ model: e.target.value })} />
          <p className="text-xs text-muted-foreground">Leave empty for {chat.default_model}.</p>
        </div>
        {v.provider === 'openai_compatible' && (
          <div className="space-y-1.5">
            <Label htmlFor="ai-url">Server URL</Label>
            <Input id="ai-url" type="url" value={v.base_url ?? ''} placeholder="http://localhost:11434/v1" onChange={(e) => set({ base_url: e.target.value })} />
            <p className="text-xs text-muted-foreground">Ollama, LM Studio, vLLM or OpenRouter. From Docker, use host.docker.internal instead of localhost.</p>
          </div>
        )}
        {v.provider === 'gemini' && (
          <label className="flex items-start gap-2 self-center text-sm">
            <Checkbox checked={!!v.vertexai} onCheckedChange={(c) => set({ vertexai: !!c })} className="mt-0.5" />
            <span>Vertex AI express mode<span className="block text-xs text-muted-foreground">Off for a Gemini API key from Google AI Studio.</span></span>
          </label>
        )}
      </div>

      {!chat.web_search && (
        <p className="flex gap-2 rounded-lg bg-warning-soft px-3 py-2 text-sm text-warning"><AlertTriangle aria-hidden className="mt-0.5 size-4 shrink-0" />
          This provider can’t search the web, so finding faculty pages and checking programs won’t work. Reading pages you add and drafting still work.</p>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="emb-provider">Embeddings provider</Label>
          <select id="emb-provider" className={selectClass} value={v.embedding_provider}
            onChange={(e) => set({ embedding_provider: e.target.value as EmbeddingProvider, embedding_model: '' })}>
            {q.data.providers.filter((p) => p.embeddings).map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
          </select>
          <p className="text-xs text-muted-foreground">Compares your interests with professors’ papers. Claude has no embeddings model.</p>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="emb-model">Embeddings model</Label>
          <Input id="emb-model" value={v.embedding_model ?? ''} placeholder={embed.default_embedding_model ?? ''} onChange={(e) => set({ embedding_model: e.target.value })} />
          <p className="text-xs text-muted-foreground">Changing it clears stored vectors; run Evaluate programs again afterwards.</p>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        {keyProviders.map((id) => (
          <KeyField key={id} info={info(id)} value={keys[id] ?? ''} onChange={(k) => setKeys({ ...keys, [id]: k })}
            onRemove={() => save.mutate({ keys: { [id]: '' } })} />
        ))}
      </div>
      <p className="flex gap-2 text-xs text-muted-foreground"><KeyRound aria-hidden className="size-3.5 shrink-0" />Keys are stored in this app’s local database and never sent back to the browser. Keep the app on localhost.</p>

      <details className="rounded-lg border border-border px-3.5 py-2.5 text-sm">
        <summary className="cursor-pointer font-medium">Prices for cost tracking</summary>
        <div className="mt-3 grid gap-3 sm:grid-cols-3">
          {([['usd_per_million_input', 'USD per 1M input tokens'], ['usd_per_million_output', 'USD per 1M output tokens'], ['usd_per_search', 'USD per web search']] as const).map(([k, label]) => (
            <div key={k} className="space-y-1.5">
              <Label htmlFor={k} className="text-xs">{label}</Label>
              <Input id={k} type="number" min={0} step="any" value={v[k] ?? 0} onChange={(e) => set({ [k]: Number(e.target.value) || 0 })} />
            </div>
          ))}
        </div>
        <p className="mt-2 text-xs text-muted-foreground">From your provider’s pricing page. Leave at 0 to skip cost estimates on jobs.</p>
      </details>

      <div className="flex flex-wrap items-center gap-2">
        <Button type="submit" disabled={!dirty || save.isPending}>{save.isPending && <Loader2 className="animate-spin" />}Save</Button>
        <Button type="button" variant="outline" disabled={dirty || runTest.isPending} title={dirty ? 'Save first' : undefined} onClick={() => runTest.mutate()}>
          {runTest.isPending ? <Loader2 className="animate-spin" /> : <PlugZap />}Test connection
        </Button>
        {test && (
          <span className="text-sm" role="status">
            <span className={test.chat === 'ok' ? 'text-success' : 'text-error'}>Model: {test.chat === 'ok' ? 'working' : test.chat}</span>
            {' · '}<span className={test.embeddings === 'ok' ? 'text-success' : 'text-error'}>Embeddings: {test.embeddings === 'ok' ? 'working' : test.embeddings}</span>
          </span>
        )}
      </div>
    </form>
  )
}

export function SettingsPage() {
  const { choice } = useTheme()
  const jobs = useQuery({ queryKey: ['jobs'], queryFn: api.jobs })
  const [exporting, setExporting] = useState(false)
  const lastEval = jobs.data?.find((j) => j.job_type === 'evaluation' && j.status === 'completed')

  // Everything the app knows about you, as one file you keep; nothing leaves your machine.
  const exportData = async () => {
    setExporting(true)
    try {
      const [profile, applications] = await Promise.all([api.profile().catch(() => null), api.applications()])
      const blob = new Blob([JSON.stringify({ exported_at: new Date().toISOString(), profile, applications }, null, 2)], { type: 'application/json' })
      const a = Object.assign(document.createElement('a'), { href: URL.createObjectURL(blob), download: `research-scout-${new Date().toISOString().slice(0, 10)}.json` })
      a.click()
      URL.revokeObjectURL(a.href)
    } catch (e) {
      toast.error('Couldn’t export your data', { description: e instanceof Error ? e.message : String(e) })
    } finally {
      setExporting(false)
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Settings" description="AI provider, appearance, research data and what the app keeps about you." />

      <Section id="appearance" title="Appearance" description="Saved in this browser only." icon={Palette}>
        <div role="group" aria-label="Colour theme" className="grid gap-2 sm:grid-cols-3">
          {THEMES.map(({ value, label, icon: Icon }) => (
            <button key={value} type="button" aria-pressed={choice === value} onClick={() => setTheme(value)}
              className={cn('flex items-center gap-3 rounded-lg border px-4 py-3 text-left text-sm font-medium transition-colors duration-(--dur-micro) focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring',
                choice === value ? 'border-signal bg-accent-soft text-foreground' : 'border-border bg-sheet text-ink-soft hover:border-input hover:text-foreground')}>
              <Icon aria-hidden className={cn('size-[18px]', choice === value ? 'text-signal' : 'text-muted-foreground')} />{label}
            </button>
          ))}
        </div>
      </Section>

      <Section id="ai" title="AI provider" description="The model that searches the web, reads official pages, drafts emails and compares research." icon={Bot}>
        <AiProvider />
      </Section>

      <Section id="search" title="Search preferences" description="Research interests, degrees and funding needs drive every match and ranking." icon={SlidersHorizontal}>
        <p className="text-sm text-ink-soft">They live on your academic profile, so matching, eligibility checks and drafts all read the same answers.</p>
        <Button variant="outline" className="mt-3" asChild><Link to="/profile">Edit in Academic Profile <ArrowRight data-icon="inline-end" /></Link></Button>
      </Section>

      <Section id="refresh" title="Research refresh" description="Deadlines and funding change each cycle; stale pages are flagged after 45 days." icon={RefreshCw}>
        <p className="text-sm text-ink-soft">
          {lastEval ? <>Programs were last evaluated {timeAgo(lastEval.completed_at ?? lastEval.created_at)}.</> : 'Programs have not been evaluated yet.'}
          {' '}Re-checking runs in the background and takes about 15 to 20 minutes.
        </p>
        <Button variant="outline" className="mt-3" asChild><Link to="/researchers#evaluate">Re-check programs <ArrowRight data-icon="inline-end" /></Link></Button>
      </Section>

      <Section id="data" title="Data management" description="Your profile and tracker stay on this machine’s database." icon={Database}>
        <div className="space-y-4">
          <div>
            <Button variant="outline" onClick={exportData} disabled={exporting}><Download />{exporting ? 'Preparing…' : 'Export my data'}</Button>
            <p className="mt-1.5 text-xs text-muted-foreground">A JSON file with your academic profile and every tracked application.</p>
          </div>
          <div>
            <p className="text-sm font-medium text-foreground">Connected sources</p>
            <dl className="mt-2 divide-y divide-border rounded-lg border border-border">
              {SOURCES.map(([name, what]) => (
                <div key={name} className="grid gap-1 px-3.5 py-2.5 text-sm sm:grid-cols-[12rem_1fr]">
                  <dt className="font-medium text-foreground">{name}</dt><dd className="text-muted-foreground">{what}</dd>
                </div>
              ))}
            </dl>
          </div>
          <p className="text-xs text-muted-foreground">Research Scout never sends emails or submits applications. Drafts are copied out and sent by you.</p>
        </div>
      </Section>
    </div>
  )
}
