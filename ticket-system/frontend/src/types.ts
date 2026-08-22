export type TicketStatus =
  | 'queued'
  | 'planning'
  | 'implementing'
  | 'reviewing'
  | 'revising'
  | 'retro'
  | 'done'
  | 'needs_human'
  | 'failed'

export interface Subtask {
  id: string
  title: string
  description: string
  acceptance_criteria: string[]
  status: string
  iterations: number
  session_id: string | null
  session_url: string | null
  pr_url: string | null
  verdict: string | null
}

export interface TicketEvent {
  id: number
  ticket_id: string
  role: string | null
  phase: string
  message: string
  level: string
  data: Record<string, unknown> | null
  created_at: string
}

export interface Plan {
  summary?: string
  risks?: string[]
  session_url?: string
  learnings_applied?: number
}

export interface Retro {
  summary?: string
  recurring_issues?: string[]
  learnings?: { kind: string; title: string; body: string }[]
  session_url?: string
}

export interface Ticket {
  id: string
  title: string
  description: string
  repo: string
  base_branch: string
  acceptance_criteria: string[]
  status: TicketStatus
  max_iterations: number
  created_at: string
  updated_at: string
  plan: Plan | null
  subtasks: Subtask[]
  pr_urls: string[]
  metrics: Record<string, number | string>
  retro: Retro | null
}

export interface Learning {
  id: number
  ticket_id: string
  kind: string
  title: string
  body: string
  hits: number
  created_at: string
}

export interface Health {
  status: string
  executor: string
  devin_configured: boolean
  max_iterations: number
}

export interface NewTicket {
  title: string
  description: string
  repo: string
  base_branch: string
  acceptance_criteria: string[]
}
