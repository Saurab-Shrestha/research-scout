// Self-check for the calendar export: `node e2e/ics.check.ts`
import assert from 'node:assert/strict'
import { toIcs } from '../src/lib/ics.ts'

const ics = toIcs([
  { uid: 'deadline-1@research-scout', date: '2026-12-01', title: 'Deadline: Toronto, PhD; apply', alarmDays: 7, url: 'https://example.edu/phd',
    description: 'Roger Grosse\nhttps://example.edu/phd ' + 'é'.repeat(60) },
  { uid: 'action-2@research-scout', date: '2026-12-31', title: 'Follow up' },
], new Date('2026-10-31T08:00:00Z'))

const lines = ics.split('\r\n')
assert.ok(ics.endsWith('\r\n') && !/[^\r]\n/.test(ics), 'CRLF line endings only')
assert.ok(lines.includes('DTSTART;VALUE=DATE:20261201') && lines.includes('DTEND;VALUE=DATE:20261202'), 'all-day event')
assert.ok(lines.includes('DTEND;VALUE=DATE:20270101'), 'end date rolls over the year')
assert.ok(lines.includes(String.raw`SUMMARY:Deadline: Toronto\, PhD\; apply`), 'commas and semicolons escaped')
assert.ok(lines.includes('TRIGGER:-P7D'), 'reminder a week before')
assert.ok(lines.includes('DTSTAMP:20261031T080000Z'))
assert.ok(lines.every((l) => new TextEncoder().encode(l).length <= 75), 'lines folded at 75 octets')
const description = lines.slice(lines.findIndex((l) => l.startsWith('DESCRIPTION:Roger'))).join('\r\n').split('\r\nURL')[0]
assert.ok(description.replace(/\r\n /g, '').includes('Roger Grosse\\nhttps://example.edu/phd é'), 'newlines escaped, folding reversible')
console.log('✓ ics export')
