import type {
  AsyncRunResponse,
  ConfigResponse,
  HealthResponse,
  MeResponse,
  RunRequest,
  RunResponse,
  StartupResponse,
  TrackerStatsResponse,
  TrackerHistoryResponse,
} from '../types/api'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

async function readJson<T>(resp: Response): Promise<T> {
  const text = await resp.text()
  const parsed = text ? JSON.parse(text) : null
  if (!resp.ok) {
    const detail = parsed && typeof parsed === 'object' && 'detail' in parsed ? parsed.detail : null
    throw new Error(String(detail || text || `Request failed (${resp.status})`))
  }
  return ((parsed ?? {}) as T)
}

export function getApiBase() {
  return API_BASE
}

export async function getHealth() {
  const resp = await fetch(`${API_BASE}/api/v1/health`)
  return readJson<HealthResponse>(resp)
}

export async function getStartup() {
  const resp = await fetch(`${API_BASE}/api/v1/startup`)
  return readJson<StartupResponse>(resp)
}

export async function getConfig() {
  const resp = await fetch(`${API_BASE}/api/v1/config`)
  return readJson<ConfigResponse>(resp)
}

export async function getMe(token: string) {
  const resp = await fetch(`${API_BASE}/api/v1/me`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  return readJson<MeResponse>(resp)
}

export async function getTrackerStats(token: string) {
  const resp = await fetch(`${API_BASE}/api/v1/tracker/stats`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  return readJson<TrackerStatsResponse>(resp)
}

export async function getTrackerHistory(token: string) {
  const resp = await fetch(`${API_BASE}/api/v1/tracker/history`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  return readJson<TrackerHistoryResponse>(resp)
}

export async function verifyFirebaseToken(idToken: string) {
  const resp = await fetch(`${API_BASE}/api/v1/auth/firebase-login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id_token: idToken }),
  })
  return readJson<MeResponse>(resp)
}

export async function runSync(token: string, body: RunRequest) {
  const resp = await fetch(`${API_BASE}/api/v1/run`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  })
  return readJson<RunResponse>(resp)
}

export async function runAsync(token: string, body: RunRequest) {
  const resp = await fetch(`${API_BASE}/api/v1/run/async`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  })
  return readJson<AsyncRunResponse>(resp)
}

export async function getRun(token: string, runId: string) {
  const resp = await fetch(`${API_BASE}/api/v1/run/${encodeURIComponent(runId)}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  return readJson<RunResponse>(resp)
}
