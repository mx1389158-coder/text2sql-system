import type { Badcase, Catalog, EvalJob, QueryRecord, SystemInfo } from '../types'

const baseUrl = import.meta.env.VITE_API_BASE_URL || '/api/v1'
const apiKeyStorage = 'nebula-text2sql-api-key'

export const apiKeyAuth = {
  get: () => window.sessionStorage.getItem(apiKeyStorage) || '',
  set: (value: string) => {
    const normalized = value.trim()
    if (normalized) window.sessionStorage.setItem(apiKeyStorage, normalized)
    else window.sessionStorage.removeItem(apiKeyStorage)
  },
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const apiKey = apiKeyAuth.get()
  const response = await fetch(`${baseUrl}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(apiKey ? { 'X-API-Key': apiKey } : {}),
      ...(init?.headers || {}),
    },
  })
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(payload.detail || '请求失败')
  }
  return response.json() as Promise<T>
}

export const api = {
  system: () => request<SystemInfo>('/system'),
  query: (question: string, strategy = 'optimized') =>
    request<QueryRecord>('/query', {
      method: 'POST',
      body: JSON.stringify({ question, strategy }),
    }),
  clarify: (id: string, answer: string) =>
    request<QueryRecord>(`/query/${id}/clarify`, {
      method: 'POST',
      body: JSON.stringify({ answer }),
    }),
  feedback: (queryId: string, rating: 'correct' | 'incorrect', comment = '') =>
    request<{ accepted: boolean }>('/feedback', {
      method: 'POST',
      body: JSON.stringify({ query_id: queryId, rating, comment }),
    }),
  catalog: () => request<Catalog>('/schema'),
  startEval: (strategy: string, datasetPath: string, model: string) =>
    request<{ job_id: string; status: string }>('/evals/run', {
      method: 'POST',
      body: JSON.stringify({ dataset_path: datasetPath, model, strategy }),
    }),
  evalJob: (id: string) => request<EvalJob>(`/evals/${id}`),
  evalJobs: () => request<{ jobs: EvalJob[] }>('/evals'),
  badcases: () => request<{ items: Badcase[] }>('/feedback'),
}

