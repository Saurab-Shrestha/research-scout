// Typed client for the FastAPI backend (/api/v1). Shapes mirror backend/app/api/v1/*.

export type Degree = 'phd' | 'thesis_masters' | 'course_masters'
export type FundingStatus =
  | 'confirmed_full' | 'confirmed_partial' | 'potential' | 'unfunded' | 'unknown' | (string & {})
export type EligibilityStatus =
  | 'eligible' | 'potentially_eligible' | 'insufficient_information' | 'ineligible' | (string & {})
export type CheckStatus = 'ok' | 'warn' | 'unknown' | 'fail'

export interface Check { name: string; status: CheckStatus; detail: string }
export interface ResearchMatch { interest: string; paper: string; year: number | null; similarity: number; publication_id: string }

export interface Opportunity {
  id: string
  title: string
  degree_type: Degree
  professor_id: string
  professor: string
  faculty_url: string | null
  university: string
  country: string | null
  program: string
  program_url: string | null
  deadline: string | null
  funding_status: FundingStatus
  funding_explanation: string
  stipend: string | null
  eligibility_status: EligibilityStatus
  excluded_reason: string | null
  scores: { research: number; funding: number; eligibility: number; availability: number; timing: number }
  overall_score: number
  explanation: { research_matches?: ResearchMatch[]; eligibility_checks?: Check[]; funding?: string; weights?: Record<string, number> }
}

export interface OpportunityDetail extends Opportunity {
  requirements: { pages?: { url: string; result: string }[]; english?: { test: string; minimum: string | null }[]; [k: string]: unknown }
  program_evidence: { field: string; value: string | null; quote: string; status: string; source_id: string }[]
}

export const STATUSES = ['shortlisted', 'researching', 'contacted', 'replied', 'applying', 'submitted',
  'interview', 'offer', 'rejected', 'declined', 'withdrawn'] as const
export type AppStatus = (typeof STATUSES)[number]
export const CLOSED: AppStatus[] = ['offer', 'rejected', 'declined', 'withdrawn']

export interface Application {
  id: string
  opportunity_id: string
  title: string
  professor: string
  professor_email: string | null
  university: string
  country: string | null
  degree_type: Degree
  status: AppStatus
  contacted_at: string | null
  deadline: string | null
  next_action: string | null
  next_action_at: string | null
  notes: string
  history: { at: string; status: string }[]
}

export interface Draft {
  id: string
  opportunity_id: string
  kind: 'email' | 'sop_outline'
  subject: string | null
  body: string
  cited_publication_ids: string[]
  warnings: string[]
  model: string
  prompt_version: string
  sources: { profile_updated_at?: string | null; publication_ids?: string[]; program_source_ids?: string[]; funding_evidence_ids?: string[] }
  created_at: string
}

export interface Publication {
  id: string; title: string; publication_year: number | null; doi: string | null; arxiv_id: string | null
  url: string | null; open_access_url: string | null; abstract: string | null; author_position: string | null
}

export interface Professor {
  id: string; name: string; title: string | null; email: string | null; faculty_url: string | null
  research_summary: string | null; openalex_id: string | null; orcid: string | null
  accepting_students: boolean | null; university_id: string | null; university: string | null
  department_id: string | null
  evidence: { id: string; source_id: string; field_name: string; value: string | null; excerpt: string; verification_status: string }[]
  publications: Publication[]
}

export interface Job {
  id: string; job_type: string; status: 'queued' | 'running' | 'completed' | 'failed' | (string & {})
  input: Record<string, unknown>; result: Record<string, unknown> | null; error_message: string | null
  attempts: number; tokens_used: number; cost_usd: number; created_at: string; completed_at: string | null
}
export interface JobEvent { id: string; event_type: string; message: string; metadata: Record<string, unknown>; created_at: string }

export interface Profile {
  id?: string
  name: string
  education: { degree: string; field: string; university: string; country: string | null; graduation_year: number | null; gpa: number | null; gpa_scale: number | null; relevant_courses: string[] }[]
  experience: { kind: 'project' | 'research' | 'publication' | 'work'; title: string; description: string | null; url: string | null; year: number | null }[]
  skills: string[]
  test_scores: { test: string; score: string; taken_on: string | null }[]
  research_interests: string[]
  career_goals: string | null
  intended_start_term: string | null
  funding_preferences: { needs_tuition_coverage: boolean; needs_living_stipend: boolean; requires_funding_at_admission: boolean; max_unfunded_cost_usd: number | null }
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) { super(message); this.status = status }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api/v1${path}`, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const data = await res.json()
      detail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)
    } catch { /* not JSON */ }
    throw new ApiError(res.status, detail || `Request failed (${res.status})`)
  }
  return res.status === 204 ? (undefined as T) : res.json()
}

export const api = {
  opportunities: (includeExcluded = true) => request<Opportunity[]>('GET', `/opportunities?include_excluded=${includeExcluded}`),
  opportunity: (id: string) => request<OpportunityDetail>('GET', `/opportunities/${id}`),
  evaluate: (body: { professor_ids?: string[] | null; degree_types?: Degree[]; force?: boolean }) =>
    request<{ job_id: string }>('POST', '/opportunities/evaluate', body),
  applications: () => request<Application[]>('GET', '/applications'),
  track: (opportunity_id: string) => request<Application>('POST', '/applications', { opportunity_id }),
  updateApplication: (id: string, body: Partial<Pick<Application, 'status' | 'contacted_at' | 'deadline' | 'next_action' | 'next_action_at' | 'notes'>>) =>
    request<Application>('PATCH', `/applications/${id}`, body),
  deleteApplication: (id: string) => request<void>('DELETE', `/applications/${id}`),
  drafts: (opportunityId: string) => request<Draft[]>('GET', `/opportunities/${opportunityId}/drafts`),
  createDraft: (opportunityId: string, kind: Draft['kind']) => request<Draft>('POST', `/opportunities/${opportunityId}/drafts`, { kind }),
  updateDraft: (id: string, body: { subject?: string | null; body?: string }) => request<Draft>('PATCH', `/drafts/${id}`, body),
  professors: () => request<Professor[]>('GET', '/professors'),
  professor: (id: string) => request<Professor>('GET', `/professors/${id}`),
  jobs: () => request<Job[]>('GET', '/research-jobs'),
  job: (id: string) => request<Job>('GET', `/research-jobs/${id}`),
  jobEvents: (id: string) => request<JobEvent[]>('GET', `/research-jobs/${id}/events`),
  startDiscovery: (body: { query?: string | null; research_areas: string[]; countries: ('US' | 'CA')[]; max_results: number; find_pages: boolean }) =>
    request<Job>('POST', '/research-jobs', body),
  ingest: (body: { url?: string | null; text?: string | null; source_type?: 'web_page' | 'social_post' }) =>
    request<{ source_id: string; canonical_url: string; created: boolean }>('POST', '/sources/ingest', body),
  extract: (sourceId: string) =>
    request<{ source_id: string; professor_id: string | null; page_kind: string; verified_fields: number; unverified_fields: number; warnings: string[] }>('POST', `/sources/${sourceId}/extract`),
  profile: () => request<Profile>('GET', '/profile'),
  saveProfile: (body: Profile) => request<Profile>('PUT', '/profile', body),
}
