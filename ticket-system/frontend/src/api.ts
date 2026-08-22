import type { Health, Learning, NewTicket, Ticket, TicketEvent } from './types'

async function json<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const detail = await response.text()
    throw new Error(`${response.status}: ${detail}`)
  }
  return (await response.json()) as T
}

export const api = {
  health: () => fetch('/api/health').then(json<Health>),

  listTickets: () => fetch('/api/tickets').then(json<Ticket[]>),

  getTicket: (id: string) => fetch(`/api/tickets/${id}`).then(json<Ticket>),

  listEvents: (id: string) => fetch(`/api/tickets/${id}/events`).then(json<TicketEvent[]>),

  listLearnings: () => fetch('/api/learnings').then(json<Learning[]>),

  createTicket: (payload: NewTicket) =>
    fetch('/api/tickets', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then(json<Ticket>),

  sendFeedback: (ticketId: string, subtaskId: string, feedback: string) =>
    fetch(`/api/tickets/${ticketId}/subtasks/${subtaskId}/feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ feedback }),
    }).then(json<{ status: string }>),
}

export function streamTicket(
  ticketId: string,
  onEvent: (event: TicketEvent) => void,
): () => void {
  const source = new EventSource(`/api/tickets/${ticketId}/stream`)
  source.addEventListener('ticket', (message) => {
    onEvent(JSON.parse((message as MessageEvent<string>).data) as TicketEvent)
  })
  return () => source.close()
}
