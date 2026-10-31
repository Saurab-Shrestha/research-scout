import type { AppStatus, CheckStatus, Degree, EligibilityStatus, FundingStatus } from './api'

export const DEGREE: Record<Degree, string> = { phd: 'PhD', thesis_masters: 'Thesis MS', course_masters: 'Course MS' }

export type Tone = 'success' | 'info' | 'warning' | 'danger' | 'neutral'

export const FUNDING: Record<string, { label: string; tone: Tone; hint: string }> = {
  confirmed_full: { label: 'Confirmed full', tone: 'success', hint: 'An official page guarantees tuition and a stipend' },
  confirmed_partial: { label: 'Confirmed partial', tone: 'info', hint: 'Official page confirms some funding' },
  potential: { label: 'Potential funding', tone: 'warning', hint: 'Usual for this degree and country, not confirmed on an official page' },
  unfunded: { label: 'Unfunded', tone: 'danger', hint: 'Official page says no funding' },
  unknown: { label: 'Funding unknown', tone: 'neutral', hint: 'No funding information found' },
}
export const funding = (s: FundingStatus) => FUNDING[s] ?? { label: s.replace(/_/g, ' '), tone: 'neutral' as Tone, hint: '' }

export const ELIGIBILITY: Record<string, { label: string; tone: Tone }> = {
  eligible: { label: 'Eligible', tone: 'success' },
  potentially_eligible: { label: 'Likely eligible', tone: 'info' },
  insufficient_information: { label: 'Needs info', tone: 'warning' },
  ineligible: { label: 'Ineligible', tone: 'danger' },
}
export const eligibility = (s: EligibilityStatus) => ELIGIBILITY[s] ?? { label: s.replace(/_/g, ' '), tone: 'neutral' as Tone }

export const CHECK_TONE: Record<CheckStatus, Tone> = { ok: 'success', warn: 'warning', unknown: 'neutral', fail: 'danger' }

export const STATUS_LABEL: Record<AppStatus, string> = {
  shortlisted: 'Shortlisted', researching: 'Researching', contacted: 'Contacted', replied: 'Replied',
  applying: 'Applying', submitted: 'Submitted', interview: 'Interview', offer: 'Offer', rejected: 'Rejected',
  declined: 'Declined', withdrawn: 'Withdrawn',
}

const DAY = 86_400_000

/** Whole days from today (local) to an ISO date; negative when past. */
export function daysUntil(iso: string | null): number | null {
  if (!iso) return null
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number)
  const today = new Date()
  const start = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate())
  return Math.round((Date.UTC(y, m - 1, d) - start) / DAY)
}

export function formatDate(iso: string | null, opts: Intl.DateTimeFormatOptions = { month: 'short', day: 'numeric' }) {
  if (!iso) return 'No date'
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number)
  return new Date(y, m - 1, d).toLocaleDateString(undefined, opts)
}

export function relativeDays(days: number | null): string {
  if (days === null) return 'No date'
  if (days === 0) return 'Today'
  if (days === 1) return 'Tomorrow'
  if (days === -1) return 'Yesterday'
  return days > 0 ? `in ${days} days` : `${-days} days ago`
}

export function urgencyTone(days: number | null): Tone {
  if (days === null) return 'neutral'
  if (days < 0) return 'danger'
  if (days <= 14) return 'warning'
  if (days <= 45) return 'info'
  return 'neutral'
}

// Mirrors backend/app/core/countries.py: the countries discovery can search, by region.
export const REGIONS: Record<string, Record<string, string>> = {
  'North America': { US: 'USA', CA: 'Canada' },
  Europe: {
    GB: 'United Kingdom', IE: 'Ireland', DE: 'Germany', NL: 'Netherlands', CH: 'Switzerland', AT: 'Austria', BE: 'Belgium',
    DK: 'Denmark', FI: 'Finland', NO: 'Norway', SE: 'Sweden', FR: 'France', ES: 'Spain', IT: 'Italy', PT: 'Portugal',
  },
  'Asia-Pacific': { AU: 'Australia', NZ: 'New Zealand', JP: 'Japan', KR: 'South Korea' },
}
export const COUNTRY: Record<string, string> = Object.assign({}, ...Object.values(REGIONS))

/** "USA & Canada" for a couple of countries, "7 countries" beyond three. */
export function countryList(codes: string[]): string {
  const names = codes.map((c) => COUNTRY[c] ?? c)
  return names.length > 3 ? `${names.length} countries` : names.join(' & ')
}

export function timeAgo(iso: string): string {
  const s = Math.round((Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)} min ago`
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`
  return `${Math.floor(s / 86400)} d ago`
}
