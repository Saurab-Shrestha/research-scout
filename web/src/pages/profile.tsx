import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { ErrorState, PageHeader, RowsSkeleton } from '@/components/app/states'
import { TagInput } from '@/components/app/tags'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { api, type Profile } from '@/lib/api'

const EMPTY: Profile = {
  name: '', education: [], experience: [], skills: [], test_scores: [], research_interests: [], career_goals: null,
  intended_start_term: null,
  funding_preferences: { needs_tuition_coverage: true, needs_living_stipend: true, requires_funding_at_admission: true, max_unfunded_cost_usd: null },
}

function Section({ title, description, children, action }: { title: string; description?: string; children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-4">
        <div className="space-y-1"><CardTitle className="font-sans text-base">{title}</CardTitle>{description && <CardDescription>{description}</CardDescription>}</div>
        {action}
      </CardHeader>
      <CardContent className="space-y-4">{children}</CardContent>
    </Card>
  )
}

function Field({ id, label, children, hint }: { id: string; label: string; children: React.ReactNode; hint?: string }) {
  return <div className="space-y-1.5"><Label htmlFor={id}>{label}</Label>{children}{hint && <p className="text-xs text-muted-foreground">{hint}</p>}</div>
}

const num = (v: string) => (v === '' ? null : Number(v))

export function ProfilePage() {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['profile'], queryFn: api.profile, retry: false })
  const [p, setP] = useState<Profile>(EMPTY)
  const [dirty, setDirty] = useState(false)
  useEffect(() => { if (q.data) { setP(q.data); setDirty(false) } }, [q.data])
  const up = (patch: Partial<Profile>) => { setP({ ...p, ...patch }); setDirty(true) }
  const save = useMutation({
    mutationFn: () => api.saveProfile(p),
    onSuccess: (d) => { qc.setQueryData(['profile'], d); setDirty(false); toast.success('Profile saved', { description: 'Re-run “Evaluate programs” to update scores.' }) },
    onError: (e) => toast.error('Couldn’t save profile', { description: e.message }),
  })
  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => { if (dirty) e.preventDefault() }
    addEventListener('beforeunload', warn)
    return () => removeEventListener('beforeunload', warn)
  }, [dirty])

  if (q.isLoading) return <RowsSkeleton rows={8} />
  if (q.isError && !(q.error as { status?: number }).status) return <ErrorState error={q.error} retry={() => q.refetch()} />
  const fp = p.funding_preferences

  return (
    <form className="space-y-6 pb-24" onSubmit={(e) => { e.preventDefault(); save.mutate() }}>
      <PageHeader title="Academic Profile" description="Used for matching, eligibility checks and drafts. Only facts here are used about you." />

      <Section title="Basics">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field id="name" label="Full name"><Input id="name" required value={p.name} onChange={(e) => up({ name: e.target.value })} /></Field>
          <Field id="term" label="Intended start" hint="e.g. Fall 2027"><Input id="term" value={p.intended_start_term ?? ''} onChange={(e) => up({ intended_start_term: e.target.value || null })} /></Field>
        </div>
        <Field id="goals" label="Career goals"><Textarea id="goals" rows={3} value={p.career_goals ?? ''} onChange={(e) => up({ career_goals: e.target.value || null })} placeholder="What you want to do after the degree" /></Field>
      </Section>

      <Section title="Research interests" description="Each interest is compared with professors’ recent papers. Be specific.">
        <TagInput id="interests" value={p.research_interests} onChange={(v) => up({ research_interests: v })} placeholder="e.g. vision-language models" />
      </Section>

      <div className="grid gap-6 lg:grid-cols-2">
        <Section title="English and tests" action={<Button type="button" variant="outline" size="sm" onClick={() => up({ test_scores: [...p.test_scores, { test: '', score: '', taken_on: null }] })}><Plus />Add</Button>}>
          {p.test_scores.length === 0 && <p className="text-sm text-muted-foreground">No tests yet. Most programs need IELTS or TOEFL; many don’t accept PTE.</p>}
          {p.test_scores.map((t, i) => (
            <div key={i} className="grid grid-cols-[1fr_6rem_auto] items-end gap-2">
              <Field id={`test-${i}`} label="Test"><Input id={`test-${i}`} value={t.test} placeholder="IELTS Academic" onChange={(e) => up({ test_scores: p.test_scores.map((x, j) => (j === i ? { ...x, test: e.target.value } : x)) })} /></Field>
              <Field id={`score-${i}`} label="Score"><Input id={`score-${i}`} value={t.score} onChange={(e) => up({ test_scores: p.test_scores.map((x, j) => (j === i ? { ...x, score: e.target.value } : x)) })} /></Field>
              <Button type="button" variant="ghost" size="icon" aria-label={`Remove ${t.test || 'test'}`} onClick={() => up({ test_scores: p.test_scores.filter((_, j) => j !== i) })}><Trash2 /></Button>
            </div>
          ))}
        </Section>

        <Section title="Funding needs" description="Opportunities that can’t meet these are hidden from your shortlist.">
          {([['needs_tuition_coverage', 'I need tuition covered'], ['needs_living_stipend', 'I need a living stipend'], ['requires_funding_at_admission', 'Funding must be confirmed at admission']] as const).map(([k, label]) => (
            <label key={k} className="flex items-center gap-2 text-sm"><Checkbox checked={fp[k]} onCheckedChange={(c) => up({ funding_preferences: { ...fp, [k]: !!c } })} />{label}</label>
          ))}
          <Field id="maxcost" label="Most I can pay myself (USD per year)"><Input id="maxcost" type="number" min={0} step={1000} value={fp.max_unfunded_cost_usd ?? ''} onChange={(e) => up({ funding_preferences: { ...fp, max_unfunded_cost_usd: num(e.target.value) } })} /></Field>
        </Section>
      </div>

      <Section title="Education" action={<Button type="button" variant="outline" size="sm" onClick={() => up({ education: [...p.education, { degree: '', field: '', university: '', country: null, graduation_year: null, gpa: null, gpa_scale: null, relevant_courses: [] }] })}><Plus />Add</Button>}>
        {p.education.map((e, i) => {
          const set = (patch: Partial<typeof e>) => up({ education: p.education.map((x, j) => (j === i ? { ...x, ...patch } : x)) })
          return (
            <div key={i} className="grid gap-3 rounded-lg border p-3 sm:grid-cols-6">
              <div className="sm:col-span-2"><Field id={`deg-${i}`} label="Degree"><Input id={`deg-${i}`} value={e.degree} onChange={(ev) => set({ degree: ev.target.value })} /></Field></div>
              <div className="sm:col-span-4"><Field id={`field-${i}`} label="Field"><Input id={`field-${i}`} value={e.field} onChange={(ev) => set({ field: ev.target.value })} /></Field></div>
              <div className="sm:col-span-3"><Field id={`uni-${i}`} label="University"><Input id={`uni-${i}`} value={e.university} onChange={(ev) => set({ university: ev.target.value })} /></Field></div>
              <div><Field id={`cty-${i}`} label="Country"><Input id={`cty-${i}`} maxLength={2} placeholder="NP" value={e.country ?? ''} onChange={(ev) => set({ country: ev.target.value.toUpperCase() || null })} /></Field></div>
              <div><Field id={`gpa-${i}`} label="GPA / grade"><Input id={`gpa-${i}`} type="number" step="0.01" value={e.gpa ?? ''} onChange={(ev) => set({ gpa: num(ev.target.value) })} /></Field></div>
              <div><Field id={`scale-${i}`} label="Out of"><Input id={`scale-${i}`} type="number" step="0.1" value={e.gpa_scale ?? ''} onChange={(ev) => set({ gpa_scale: num(ev.target.value) })} /></Field></div>
              <div className="sm:col-span-6 flex justify-between">
                <p className="text-xs text-muted-foreground">{e.gpa_scale && e.gpa_scale !== 4 ? 'GPA minimums are on a 4.0 scale; add a WES-converted entry to enable GPA checks.' : ''}</p>
                <Button type="button" variant="ghost" size="sm" className="text-destructive hover:text-destructive" onClick={() => up({ education: p.education.filter((_, j) => j !== i) })}><Trash2 />Remove</Button>
              </div>
            </div>
          )
        })}
      </Section>

      <Section title="Experience" description="Work, research and projects. Drafts only mention what’s written here." action={<Button type="button" variant="outline" size="sm" onClick={() => up({ experience: [...p.experience, { kind: 'project', title: '', description: null, url: null, year: null }] })}><Plus />Add</Button>}>
        {p.experience.map((x, i) => {
          const set = (patch: Partial<typeof x>) => up({ experience: p.experience.map((y, j) => (j === i ? { ...y, ...patch } : y)) })
          return (
            <div key={i} className="grid gap-3 rounded-lg border p-3 sm:grid-cols-6">
              <div className="sm:col-span-1">
                <Field id={`kind-${i}`} label="Type">
                  <Select value={x.kind} onValueChange={(v) => set({ kind: v as typeof x.kind })}>
                    <SelectTrigger id={`kind-${i}`} className="w-full"><SelectValue /></SelectTrigger>
                    <SelectContent>{['work', 'research', 'project', 'publication'].map((k) => <SelectItem key={k} value={k} className="capitalize">{k}</SelectItem>)}</SelectContent>
                  </Select>
                </Field>
              </div>
              <div className="sm:col-span-4"><Field id={`title-${i}`} label="Title"><Input id={`title-${i}`} value={x.title} onChange={(ev) => set({ title: ev.target.value })} /></Field></div>
              <div><Field id={`year-${i}`} label="Year"><Input id={`year-${i}`} type="number" value={x.year ?? ''} onChange={(ev) => set({ year: num(ev.target.value) })} /></Field></div>
              <div className="sm:col-span-6"><Field id={`desc-${i}`} label="What you did and the result"><Textarea id={`desc-${i}`} rows={3} value={x.description ?? ''} onChange={(ev) => set({ description: ev.target.value || null })} /></Field></div>
              <div className="sm:col-span-6 flex justify-end"><Button type="button" variant="ghost" size="sm" className="text-destructive hover:text-destructive" onClick={() => up({ experience: p.experience.filter((_, j) => j !== i) })}><Trash2 />Remove</Button></div>
            </div>
          )
        })}
      </Section>

      <Section title="Skills"><TagInput id="skills" value={p.skills} onChange={(v) => up({ skills: v })} placeholder="Add a skill" /></Section>

      <div className="fixed inset-x-0 bottom-0 z-10 border-t bg-background/90 backdrop-blur lg:left-60">
        <div className="mx-auto flex max-w-7xl items-center justify-end gap-3 px-4 py-3 sm:px-6 lg:px-8">
          <span className="text-sm text-muted-foreground" aria-live="polite">{dirty ? 'Unsaved changes' : 'All changes saved'}</span>
          <Button type="button" variant="ghost" disabled={!dirty} onClick={() => { if (q.data) setP(q.data); setDirty(false) }}>Discard</Button>
          <Button type="submit" disabled={!dirty || save.isPending}>{save.isPending ? 'Saving…' : 'Save profile'}</Button>
        </div>
      </div>
    </form>
  )
}
