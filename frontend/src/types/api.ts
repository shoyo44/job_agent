export type HealthResponse = {
  status: string
  service: string
  startup_overall_ok?: boolean
}

export type StartupCheck = {
  required?: boolean
  configured?: boolean
  ok?: boolean
  message?: string
  model?: string
  path?: string
  db?: string
  collection?: string
}

export type StartupResponse = {
  service?: string
  overall_ok?: boolean
  cloudflare_warning?: boolean
  checked_at?: string
  checks?: Record<string, StartupCheck>
}

export type ConfigResponse = Record<string, unknown>

export type MeResponse = {
  uid: string
  email: string
  name: string
  picture: string
}

export type TrackerStatsResponse = {
  stats: Record<string, unknown>
  applied_today: unknown
}

export type TrackerHistoryRecord = {
  job_id?: string
  title?: string
  company?: string
  location?: string
  status?: string
  date_applied?: string
  confidence_score?: number
  notes?: string
  platform?: string
}

export type TrackerHistoryResponse = {
  backend: {
    type: string
    connected: boolean
    db?: string
    collection?: string
    path?: string
  }
  total_recent: number
  records: TrackerHistoryRecord[]
}

export type RunRequest = {
  goal: string
  config_only: boolean
  dry_run: boolean
  easy_apply_only: boolean
  max_scraped_jobs: number
  max_scoring_jobs: number
  max_applications: number
  submission_target_successes: number
  max_approved_candidates: number
  work_mode_preference?: "any" | "remote" | "onsite" | "hybrid"
  linkedin_email?: string
  linkedin_password?: string
  resume_file_name?: string
  resume_file_b64?: string
}

export type RunResponse = {
  run_id: string
  status: string
  message: string
  payload?: Record<string, unknown>
}

export type AsyncRunResponse = {
  run_id: string
  status: string
}


