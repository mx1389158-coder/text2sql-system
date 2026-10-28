export type TraceEvent = {
  stage: string
  status: string
  elapsed_ms: number
  detail: Record<string, unknown>
}

export type QueryRecord = {
  query_id: string
  trace_id: string
  question: string
  intent: 'QUERY' | 'META' | 'CLARIFY' | 'REJECT'
  status: 'running' | 'clarification_required' | 'completed' | 'rejected' | 'failed'
  clarification?: { key: string; question: string; options: string[] }
  schema_evidence?: {
    selected_tables: string[]
    join_path_tables: string[]
    table_scores: Record<string, number>
    mschema: string
    estimated_tokens: number
    semantic_definitions: string[]
    selected_columns: string[]
    confidence: number
    expanded: boolean
  }
  sql?: string
  result?: { columns: string[]; rows: Record<string, unknown>[]; truncated: boolean; elapsed_ms: number }
  explanation?: string
  assumptions: string[]
  error_code?: string
  error_message?: string
  repair_rounds: number
  repair_succeeded: boolean
  model_calls: number
  prompt_tokens: number
  completion_tokens: number
  cached: boolean
  trace: TraceEvent[]
}

export type EvalSummary = {
  total: number
  sql_valid_rate: number
  execution_accuracy: number
  test_suite_accuracy: number
  schema_recall_at_k: number
  column_recall_at_k: number
  clarification_accuracy: number
  safety_true_positive_rate: number
  safety_false_positive_rate: number
  repair_gain: number
  p50_latency_ms: number
  p95_latency_ms: number
  model_calls: number
  prompt_tokens: number
  completion_tokens: number
  failures: Array<Record<string, unknown>>
  samples: Array<Record<string, unknown>>
}

export type EvalJob = {
  job_id: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  summary?: EvalSummary & { report?: string; strategy?: string; model?: string; experiment_id?: string }
  error?: string
  created_at?: string
  updated_at?: string
}

export type Badcase = {
  query_id: string
  rating: 'correct' | 'incorrect'
  category?: string
  corrected_sql?: string
  comment?: string
  question: string
  predicted_sql?: string
  trace_id: string
  created_at: string
  training_status: string
}

export type Catalog = {
  database_id: string
  version: string
  schema: string
  tables: Array<{
    name: string
    description: string
    aliases: string[]
    columns: Array<{ name: string; data_type: string; description: string; primary_key: boolean }>
    foreign_keys: Array<{ column: string; referred_table: string; referred_column: string }>
  }>
}

