import { useQuery } from '@tanstack/react-query'
import { CalendarPlus } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { api, CLOSED, type Application, type Opportunity } from '@/lib/api'
import { daysUntil, DEGREE } from '@/lib/format'
import { downloadIcs, type CalendarEvent } from '@/lib/ics'

/** Upcoming program deadlines (one per program and degree) plus the next action on every open application. */
export function calendarEvents(opps: Opportunity[], apps: Application[]): CalendarEvent[] {
  const open = apps.filter((a) => !CLOSED.includes(a.status))
  const tracked = new Set(open.map((a) => a.opportunity_id))
  const upcoming = opps.filter((o) => o.deadline && daysUntil(o.deadline)! >= 0 && (!o.excluded_reason || tracked.has(o.id)))
  const programs = Map.groupBy(upcoming, (o) => `${o.university}|${o.degree_type}|${o.deadline}`)
  const deadlines = [...programs.values()].map((group): CalendarEvent => {
    const o = group[0]
    return {
      uid: `deadline-${o.id}@research-scout`, date: o.deadline!, alarmDays: 7, url: o.program_url,
      title: `Deadline: ${o.university}, ${DEGREE[o.degree_type]}`,
      description: `${o.program}\nProfessors: ${group.map((x) => x.professor).join(', ')}\nCheck the official page before relying on this date.`,
    }
  })
  const actions = open.filter((a) => a.next_action && a.next_action_at && daysUntil(a.next_action_at)! >= 0).map((a): CalendarEvent => ({
    uid: `action-${a.id}@research-scout`, date: a.next_action_at!, alarmDays: 1,
    title: `${a.next_action} (${a.professor})`, description: `${a.university}, ${DEGREE[a.degree_type]}`,
  }))
  return [...deadlines, ...actions].sort((a, b) => a.date.localeCompare(b.date))
}

export function CalendarExportButton({ size = 'sm' }: { size?: 'sm' | 'default' }) {
  const opps = useQuery({ queryKey: ['opportunities'], queryFn: () => api.opportunities(true) })
  const apps = useQuery({ queryKey: ['applications'], queryFn: api.applications })
  const events = calendarEvents(opps.data ?? [], apps.data ?? [])
  return (
    <Button variant="outline" size={size} disabled={!opps.data || !apps.data || events.length === 0}
      title={events.length === 0 ? 'No upcoming deadlines or dated actions yet' : undefined}
      onClick={() => {
        downloadIcs(events)
        toast.success(`Exported ${events.length} calendar events`, { description: 'Open the file to add them to your calendar. Export again after changes; events update instead of duplicating.' })
      }}>
      <CalendarPlus />Add to calendar
    </Button>
  )
}
