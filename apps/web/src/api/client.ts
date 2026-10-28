import type { Badcase, Catalog, EvalJob, QueryRecord } from '../types'

const baseUrl = import.meta.env.VITE_API_BASE_URL || '/api/v1'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
  })
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(payload.detail || '请求失败')
  }
  return response.json() as Promise<T>
}

export const api = {
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
  startEval: (strategy: string) =>
    request<{ job_id: string; status: string }>('/evals/run', {
      method: 'POST',
      body: JSON.stringify({ dataset_path: 'data/processed/smoke.jsonl', model: 'demo', strategy }),
    }),
  evalJob: (id: string) => request<EvalJob>(`/evals/${id}`),
  evalJobs: () => request<{ jobs: EvalJob[] }>('/evals'),
  badcases: () => request<{ items: Badcase[] }>('/feedback'),
}

