// iCalendar (RFC 5545) export of deadlines and next actions, so reminders live in the user's own calendar.
// No imports, so `node web/e2e/ics.check.ts` can run it directly.

export interface CalendarEvent {
  uid: string          // stable, so re-importing updates events instead of duplicating them
  date: string         // YYYY-MM-DD, an all-day event
  title: string
  description?: string
  url?: string | null
  alarmDays?: number   // remind this many days before
}

const escape = (s: string) => s.replace(/\\/g, '\\\\').replace(/;/g, '\\;').replace(/,/g, '\\,').replace(/\r?\n/g, '\\n')
const ymd = (iso: string) => iso.slice(0, 10).replace(/-/g, '')

function nextDay(iso: string) {
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, d + 1)).toISOString().slice(0, 10)
}

/** Lines longer than 75 octets continue on the next line after a space (RFC 5545 §3.1). */
function fold(line: string) {
  const bytes = new TextEncoder()
  if (bytes.encode(line).length <= 75) return line
  const parts: string[] = []
  let cur = ''
  for (const ch of line) {
    if (bytes.encode(cur + ch).length > (parts.length ? 74 : 75)) { parts.push(cur); cur = '' }
    cur += ch
  }
  return [...parts, cur].join('\r\n ')
}

export function toIcs(events: CalendarEvent[], now = new Date()): string {
  const stamp = now.toISOString().replace(/[-:]/g, '').replace(/\.\d+/, '')
  const lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Research Scout//Deadlines//EN', 'CALSCALE:GREGORIAN', 'X-WR-CALNAME:Research Scout']
  for (const e of events) {
    lines.push('BEGIN:VEVENT', `UID:${e.uid}`, `DTSTAMP:${stamp}`,
      `DTSTART;VALUE=DATE:${ymd(e.date)}`, `DTEND;VALUE=DATE:${ymd(nextDay(e.date))}`, `SUMMARY:${escape(e.title)}`)
    if (e.description) lines.push(`DESCRIPTION:${escape(e.description)}`)
    if (e.url) lines.push(`URL:${e.url}`)
    if (e.alarmDays) lines.push('BEGIN:VALARM', 'ACTION:DISPLAY', `DESCRIPTION:${escape(e.title)}`, `TRIGGER:-P${e.alarmDays}D`, 'END:VALARM')
    lines.push('END:VEVENT')
  }
  lines.push('END:VCALENDAR')
  return lines.map(fold).join('\r\n') + '\r\n'
}

export function downloadIcs(events: CalendarEvent[], filename = 'research-scout.ics') {
  const blob = new Blob([toIcs(events)], { type: 'text/calendar;charset=utf-8' })
  const a = Object.assign(document.createElement('a'), { href: URL.createObjectURL(blob), download: filename })
  a.click()
  URL.revokeObjectURL(a.href)
}
