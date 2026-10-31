import { useQuery } from '@tanstack/react-query'
import { ArrowRight, Database, Download, Monitor, Moon, Palette, RefreshCw, SlidersHorizontal, Sun } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import { PageHeader } from '@/components/app/states'
import { setTheme, useTheme, type ThemeChoice } from '@/components/app/theme'
import { Button } from '@/components/ui/button'
import { api } from '@/lib/api'
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
      <PageHeader title="Settings" description="Appearance, research data and what the app keeps about you." />

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
