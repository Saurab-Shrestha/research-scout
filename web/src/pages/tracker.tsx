import { DndContext, DragOverlay, KeyboardSensor, PointerSensor, useDraggable, useDroppable, useSensor, useSensors, type Announcements, type DragEndEvent, type KeyboardCoordinateGetter, type UniqueIdentifier } from '@dnd-kit/core'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Archive, GripVertical, History, KanbanSquare, Mail, MoreHorizontal, Table2, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import { useOpportunityParam } from '@/components/app/opportunity-sheet'
import { DeadlineChip } from '@/components/app/pills'
import { EmptyState, ErrorState, PageHeader, RowsSkeleton } from '@/components/app/states'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { api, CLOSED, STATUSES, type Application, type AppStatus } from '@/lib/api'
import { daysUntil, DEGREE, formatDate, relativeDays, STATUS_LABEL, urgencyTone } from '@/lib/format'
import { cn } from '@/lib/utils'

const COLUMNS: { id: string; label: string; statuses: AppStatus[]; hint: string }[] = [
  { id: 'shortlisted', label: 'Shortlisted', statuses: ['shortlisted', 'researching'], hint: 'Read their papers' },
  { id: 'contacted', label: 'Contacted', statuses: ['contacted'], hint: 'Waiting for a reply' },
  { id: 'replied', label: 'Replied', statuses: ['replied'], hint: 'Professor responded' },
  { id: 'applying', label: 'Applying', statuses: ['applying'], hint: 'Application in progress' },
  { id: 'submitted', label: 'Submitted', statuses: ['submitted', 'interview'], hint: 'Awaiting decision' },
  { id: 'closed', label: 'Closed', statuses: CLOSED, hint: 'Offer, rejected or withdrawn' },
]
const DROP_STATUS: Record<string, AppStatus> = { shortlisted: 'shortlisted', contacted: 'contacted', replied: 'replied', applying: 'applying', submitted: 'submitted' }

function useUpdate() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: Parameters<typeof api.updateApplication>[1] }) => api.updateApplication(id, body),
    onMutate: async ({ id, body }) => {
      await qc.cancelQueries({ queryKey: ['applications'] })
      const prev = qc.getQueryData<Application[]>(['applications'])
      qc.setQueryData<Application[]>(['applications'], (old) => old?.map((a) => (a.id === id ? { ...a, ...body } as Application : a)))
      return { prev }
    },
    onError: (e, _v, ctx) => { qc.setQueryData(['applications'], ctx?.prev); toast.error('Couldn’t save', { description: e.message }) },
    onSettled: () => qc.invalidateQueries({ queryKey: ['applications'] }),
  })
}

function CardBody({ a }: { a: Application }) {
  const days = daysUntil(a.next_action_at)
  const tone = urgencyTone(days)
  return (
    <>
      <p className="font-medium leading-snug">{a.professor}</p>
      <p className="text-xs text-muted-foreground">{a.university} · {DEGREE[a.degree_type]}</p>
      {(CLOSED.includes(a.status) || a.status === 'researching' || a.status === 'interview') && (
        <span className="mt-1 inline-block rounded bg-muted px-1.5 py-0.5 text-[11px] font-medium">{STATUS_LABEL[a.status]}</span>
      )}
      {a.next_action && !CLOSED.includes(a.status) && (
        <div className={cn('mt-2 rounded-md px-2 py-1.5 text-xs', tone === 'danger' ? 'bg-error-soft text-error' : tone === 'warning' ? 'bg-warning-soft text-warning' : 'bg-muted text-muted-foreground')}>
          <p className="font-medium">{a.next_action}</p>
          {a.next_action_at && <p className="tabular">{days! < 0 ? `Overdue by ${-days!} days` : `Due ${relativeDays(days)}`} · {formatDate(a.next_action_at)}</p>}
        </div>
      )}
      <div className="mt-2"><DeadlineChip date={a.deadline} compact /></div>
    </>
  )
}

function KanbanCard({ a, onEdit }: { a: Application; onEdit: () => void }) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({ id: a.id })
  const update = useUpdate()
  const { open } = useOpportunityParam()
  // Pointer drag works anywhere on the card; keyboard drag uses the grip (Space to lift, arrows, Space to drop).
  // The card itself is a plain button that opens the editor, so nothing interactive is nested.
  return (
    <div ref={setNodeRef} onPointerDown={listeners?.onPointerDown as React.PointerEventHandler | undefined}
      className={cn('group relative cursor-grab rounded-lg border bg-card shadow-xs transition-[box-shadow,border-color] duration-150 hover:border-primary/40 hover:shadow-sm active:cursor-grabbing', isDragging && 'opacity-40')}>
      <button type="button" onClick={onEdit} className="block w-full rounded-lg p-3 pr-9 text-left focus-visible:outline-2 focus-visible:outline-ring">
        <CardBody a={a} />
      </button>
      <button type="button" {...attributes} onKeyDown={listeners?.onKeyDown as React.KeyboardEventHandler | undefined} aria-label={`Move ${a.professor} (${STATUS_LABEL[a.status]}). Press space to pick up.`}
        className="absolute bottom-2 right-1.5 grid size-8 place-items-center rounded-md text-muted-foreground opacity-60 hover:bg-muted group-hover:opacity-100 focus-visible:opacity-100 focus-visible:outline-2 focus-visible:outline-ring">
        <GripVertical aria-hidden className="size-4" />
      </button>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon" className="absolute right-1 top-1 size-8 opacity-60 group-hover:opacity-100 focus-visible:opacity-100" aria-label={`Actions for ${a.professor}`}
            onPointerDown={(e) => e.stopPropagation()}>
            <MoreHorizontal className="size-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" onClick={(e) => e.stopPropagation()}>
          <DropdownMenuItem onSelect={() => open(a.opportunity_id)}>View opportunity</DropdownMenuItem>
          <DropdownMenuItem asChild><Link to={`/drafts?for=${a.opportunity_id}`}><Mail />Write email</Link></DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuLabel className="text-xs text-muted-foreground">Move to</DropdownMenuLabel>
          {STATUSES.filter((s) => s !== a.status).map((s) => (
            <DropdownMenuItem key={s} onSelect={() => update.mutate({ id: a.id, body: { status: s } })}>{STATUS_LABEL[s]}</DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  )
}

function Column({ col, items, onEdit }: { col: (typeof COLUMNS)[number]; items: Application[]; onEdit: (a: Application) => void }) {
  const { setNodeRef, isOver } = useDroppable({ id: col.id })
  return (
    <section aria-label={col.label} ref={setNodeRef}
      className={cn('flex w-72 shrink-0 flex-col gap-2 rounded-xl border bg-muted/40 p-2 transition-colors duration-150', isOver && 'border-primary/50 bg-accent/60', col.id === 'closed' && 'bg-muted/20')}>
      <header className="flex items-center justify-between px-1.5 pt-1">
        <div>
          <h2 className="font-sans text-sm font-semibold">{col.label} <span className="font-normal text-muted-foreground tabular">{items.length}</span></h2>
          <p className="text-[11px] text-muted-foreground">{col.hint}</p>
        </div>
        {col.id === 'closed' && <Archive aria-hidden className="size-4 text-muted-foreground" />}
      </header>
      <div className="flex min-h-24 flex-col gap-2">
        {items.map((a) => <KanbanCard key={a.id} a={a} onEdit={() => onEdit(a)} />)}
        {items.length === 0 && <p className="rounded-lg border border-dashed px-3 py-6 text-center text-xs text-muted-foreground">Drop here</p>}
      </div>
    </section>
  )
}

function EditDialog({ a, onClose }: { a: Application | null; onClose: () => void }) {
  const update = useUpdate()
  const qc = useQueryClient()
  const remove = useMutation({
    mutationFn: (id: string) => api.deleteApplication(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['applications'] }); toast.success('Removed from tracker'); onClose() },
  })
  const [form, setForm] = useState<Partial<Application>>({})
  const v = { ...a, ...form } as Application
  if (!a) return null
  const save = () => {
    update.mutate({ id: a.id, body: { status: v.status, next_action: v.next_action, next_action_at: v.next_action_at || null, deadline: v.deadline || null, notes: v.notes } })
    onClose()
  }
  return (
    <Dialog open onOpenChange={(o) => { if (!o) { setForm({}); onClose() } }}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="font-heading text-xl">{a.professor}</DialogTitle>
          <DialogDescription>{a.university} · {DEGREE[a.degree_type]}{a.professor_email ? ` · ${a.professor_email}` : ''}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="status">Status</Label>
            <Select value={v.status} onValueChange={(s) => setForm({ ...form, status: s as AppStatus })}>
              <SelectTrigger id="status" className="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>{STATUSES.map((s) => <SelectItem key={s} value={s}>{STATUS_LABEL[s]}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="deadline">Application deadline</Label>
            <Input id="deadline" type="date" value={v.deadline ?? ''} onChange={(e) => setForm({ ...form, deadline: e.target.value })} />
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="next">Next action</Label>
            <Input id="next" value={v.next_action ?? ''} onChange={(e) => setForm({ ...form, next_action: e.target.value })} placeholder="e.g. Follow up if no reply" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="due">Due</Label>
            <Input id="due" type="date" value={v.next_action_at ?? ''} onChange={(e) => setForm({ ...form, next_action_at: e.target.value })} />
          </div>
          <div className="space-y-1.5">
            <Label>Contacted</Label>
            <p className="flex h-9 items-center text-sm text-muted-foreground">{a.contacted_at ? formatDate(a.contacted_at, { month: 'short', day: 'numeric', year: 'numeric' }) : 'Not yet'}</p>
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="notes">Notes</Label>
            <Textarea id="notes" rows={4} value={v.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} placeholder="Reply details, who you spoke to, what to mention next" />
          </div>
        </div>
        {a.history.length > 0 && (
          <details className="text-sm">
            <summary className="cursor-pointer text-muted-foreground">History ({a.history.length})</summary>
            <ol className="mt-2 space-y-1 border-l pl-3">
              {a.history.map((h, i) => <li key={i} className="text-xs"><span className="font-medium">{STATUS_LABEL[h.status as AppStatus] ?? h.status}</span> <span className="text-muted-foreground">· {new Date(h.at).toLocaleString()}</span></li>)}
            </ol>
          </details>
        )}
        <DialogFooter className="sm:justify-between">
          <Button variant="ghost" className="text-destructive hover:text-destructive" onClick={() => { if (confirm(`Remove ${a.professor} from the tracker? Drafts are kept.`)) remove.mutate(a.id) }}>
            <Trash2 aria-hidden />Remove
          </Button>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => { setForm({}); onClose() }}>Cancel</Button>
            <Button onClick={() => { save(); setForm({}) }}>Save</Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

const VIEWS = [['board', 'Board', KanbanSquare], ['table', 'Table', Table2], ['activity', 'Activity', History]] as const
type View = (typeof VIEWS)[number][0]

function TrackerTable({ apps, onEdit }: { apps: Application[]; onEdit: (a: Application) => void }) {
  const rows = [...apps].sort((a, b) => (a.next_action_at ?? '9').localeCompare(b.next_action_at ?? '9'))
  return (
    <div className="sheet overflow-x-auto">
      <table className="w-full min-w-[760px] text-left text-sm">
        <thead>
          <tr className="border-b border-border text-xs text-muted-foreground">
            {['Professor', 'Program', 'Stage', 'Next action', 'Deadline', 'Last contact'].map((h) => <th key={h} scope="col" className="px-4 py-3 font-medium">{h}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((a) => {
            const days = daysUntil(a.next_action_at)
            return (
              <tr key={a.id} className="border-b border-border align-top last:border-b-0 hover:bg-well/60">
                <td className="px-4 py-3">
                  <button type="button" onClick={() => onEdit(a)} className="text-left font-medium text-foreground hover:text-signal hover:underline focus-visible:outline-2 focus-visible:outline-ring">{a.professor}</button>
                  <p className="text-xs text-muted-foreground">{a.university}</p>
                </td>
                <td className="px-4 py-3 text-ink-soft">{DEGREE[a.degree_type]}</td>
                <td className="px-4 py-3"><span className="rounded-md bg-well px-2 py-0.5 text-xs font-medium text-foreground">{STATUS_LABEL[a.status]}</span></td>
                <td className="px-4 py-3">
                  <p className="text-foreground">{a.next_action ?? '—'}</p>
                  {a.next_action_at && <p className={cn('num text-xs', days! < 0 ? 'text-error' : days! <= 2 ? 'text-warning' : 'text-muted-foreground')}>{days! < 0 ? `Overdue by ${-days!} days` : `Due ${relativeDays(days)}`}</p>}
                </td>
                <td className="px-4 py-3"><DeadlineChip date={a.deadline} /></td>
                <td className="num px-4 py-3 text-ink-soft">{a.contacted_at ? formatDate(a.contacted_at, { month: 'short', day: 'numeric', year: 'numeric' }) : 'Not yet'}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

/** Every recorded stage change across applications, newest first. */
function ActivityLog({ apps }: { apps: Application[] }) {
  const events = apps.flatMap((a) => a.history.map((h) => ({ ...h, a }))).sort((x, y) => y.at.localeCompare(x.at))
  if (events.length === 0) return <p className="text-muted-foreground">No activity recorded yet.</p>
  return (
    <ol className="sheet relative space-y-0 p-5">
      {events.map((e, i) => (
        <li key={i} className="relative grid grid-cols-[1.25rem_1fr] gap-3 pb-4 last:pb-0">
          {i < events.length - 1 && <span aria-hidden className="absolute top-4 bottom-0 left-[5px] w-px bg-border" />}
          <span aria-hidden className="mt-1.5 size-[11px] rounded-full border-2 border-signal bg-sheet" />
          <div className="flex flex-wrap items-baseline justify-between gap-x-4">
            <p className="text-sm text-foreground">
              {e.status === 'shortlisted' && i === events.findLastIndex((x) => x.a.id === e.a.id) ? 'Saved' : 'Moved to'} <span className="font-medium">{STATUS_LABEL[e.status as AppStatus] ?? e.status}</span>
              <span className="text-muted-foreground"> · {e.a.professor}, {e.a.university}</span>
            </p>
            <time dateTime={e.at} className="text-xs text-muted-foreground">{new Date(e.at).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}</time>
          </div>
        </li>
      ))}
    </ol>
  )
}

const COLUMN_STEP = 300  // column width (w-72) plus gap
/** Arrow keys move a lifted card one column at a time instead of dnd-kit's default 25px nudge. */
const columnStep: KeyboardCoordinateGetter = (event, { currentCoordinates: c }) => {
  const step = { ArrowRight: [COLUMN_STEP, 0], ArrowLeft: [-COLUMN_STEP, 0], ArrowDown: [0, 60], ArrowUp: [0, -60] }[event.code]
  if (!step) return undefined
  event.preventDefault()
  return { x: c.x + step[0], y: c.y + step[1] }
}

export function TrackerPage() {
  const q = useQuery({ queryKey: ['applications'], queryFn: api.applications })
  const update = useUpdate()
  const [editing, setEditing] = useState<Application | null>(null)
  const [dragging, setDragging] = useState<Application | null>(null)
  const [closing, setClosing] = useState<Application | null>(null)
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { keyboardCodes: { start: ['Space'], cancel: ['Escape'], end: ['Space', 'Enter'] }, coordinateGetter: columnStep }))
  const apps = q.data ?? []
  const [params, setParams] = useSearchParams()
  const view: View = VIEWS.some(([v]) => v === params.get('view')) ? params.get('view') as View : 'board'
  const setView = (v: View) => setParams((p) => { if (v === 'board') p.delete('view'); else p.set('view', v); return p }, { replace: true })

  const name = (id: UniqueIdentifier) => apps.find((x) => x.id === id)?.professor ?? 'Card'
  const column = (id?: UniqueIdentifier) => COLUMNS.find((c) => c.id === id)?.label ?? 'no stage'
  const announcements: Announcements = {
    onDragStart: ({ active }) => `Picked up ${name(active.id)}.`,
    onDragOver: ({ active, over }) => `${name(active.id)} is over ${column(over?.id)}.`,
    onDragEnd: ({ active, over }) => `${name(active.id)} dropped in ${column(over?.id)}.`,
    onDragCancel: ({ active }) => `Cancelled. ${name(active.id)} stays where it was.`,
  }

  const onDragEnd = ({ active, over }: DragEndEvent) => {
    setDragging(null)
    if (!over) return
    const a = apps.find((x) => x.id === active.id)
    const col = COLUMNS.find((c) => c.id === over.id)
    if (!a || !col || col.statuses.includes(a.status)) return
    if (col.id === 'closed') { setClosing(a); return }  // offer, rejected, declined and withdrawn mean different things
    update.mutate({ id: a.id, body: { status: DROP_STATUS[col.id] } })
    toast.success(`Moved to ${col.label}`, { description: col.id === 'contacted' ? 'Contact date recorded; follow-up suggested in 10 days.' : undefined })
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Application Tracker" description="Drag cards between stages, or use a card’s menu. With a keyboard, focus the grip and press space. Each move updates the suggested next step."
        actions={apps.length > 0 && (
          <div role="group" aria-label="View" className="inline-flex rounded-lg border border-border bg-sheet p-0.5">
            {VIEWS.map(([v, label, Icon]) => (
              <button key={v} type="button" aria-pressed={view === v} onClick={() => setView(v)}
                className={cn('inline-flex h-8 items-center gap-1.5 rounded-md px-3 text-sm font-medium focus-visible:outline-2 focus-visible:outline-ring',
                  view === v ? 'bg-signal text-signal-ink' : 'text-muted-foreground hover:text-foreground')}>
                <Icon aria-hidden className="size-4" />{label}
              </button>
            ))}
          </div>
        )} />
      {q.isError ? <ErrorState error={q.error} retry={() => q.refetch()} /> : q.isLoading ? <RowsSkeleton rows={4} /> : apps.length === 0 ? (
        <EmptyState icon={KanbanSquare} title="Your pipeline is empty" action={<Button asChild><Link to="/opportunities">Browse opportunities</Link></Button>}>
          Open an opportunity and choose “Add to shortlist” to start.
        </EmptyState>
      ) : view === 'table' ? <TrackerTable apps={apps} onEdit={setEditing} />
        : view === 'activity' ? <ActivityLog apps={apps} /> : (
        <DndContext sensors={sensors} accessibility={{ announcements, screenReaderInstructions: { draggable: 'Press space to pick up the card. Use left and right arrows to change stage, space to drop, escape to cancel.' } }} onDragStart={(e) => setDragging(apps.find((a) => a.id === e.active.id) ?? null)} onDragEnd={onDragEnd} onDragCancel={() => setDragging(null)}>
          <div className="-mx-4 overflow-x-auto px-4 pb-4 sm:-mx-6 sm:px-6 lg:-mx-8 lg:px-8">
            <div className="flex gap-3">
              {COLUMNS.map((col) => <Column key={col.id} col={col} items={apps.filter((a) => col.statuses.includes(a.status))} onEdit={setEditing} />)}
            </div>
          </div>
          <DragOverlay>{dragging && <div className="w-72 rotate-1 rounded-lg border bg-card p-3 shadow-lg"><CardBody a={dragging} /></div>}</DragOverlay>
        </DndContext>
      )}
      <EditDialog key={editing?.id} a={editing} onClose={() => setEditing(null)} />
      <Dialog open={!!closing} onOpenChange={(o) => !o && setClosing(null)}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle className="font-heading text-xl">How did it end?</DialogTitle>
            <DialogDescription>{closing?.professor} · {closing?.university}</DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-2">
            {CLOSED.map((s) => (
              <Button key={s} variant={s === 'offer' ? 'default' : 'outline'} onClick={() => { update.mutate({ id: closing!.id, body: { status: s } }); toast.success(`Marked as ${STATUS_LABEL[s].toLowerCase()}`); setClosing(null) }}>
                {STATUS_LABEL[s]}
              </Button>
            ))}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
