import { useState } from 'react'
import type { RunRequest } from '../types/api'

export const DEFAULT_RUN_FORM: RunRequest = {
  goal: 'AI Engineer in Bangalore easy apply only',
  config_only: false,
  dry_run: true,
  easy_apply_only: true,
  max_scraped_jobs: 10,
  max_scoring_jobs: 5,
  max_applications: 1,
  submission_target_successes: 1,
  max_approved_candidates: 3,
  work_mode_preference: "any",
}

export function useRunForm(initial: RunRequest = DEFAULT_RUN_FORM) {
  const [form, setForm] = useState<RunRequest>(initial)

  function setField<K extends keyof RunRequest>(key: K, value: RunRequest[K]) {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  return { form, setForm, setField }
}


