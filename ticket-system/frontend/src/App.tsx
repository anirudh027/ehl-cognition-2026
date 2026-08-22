import { useCallback, useEffect, useState } from 'react'
import './App.css'
import { api, streamTicket } from './api'
import { TicketDetail } from './components/TicketDetail'
import { TicketForm } from './components/TicketForm'
import type { Health, Learning, NewTicket, Ticket, TicketEvent } from './types'

export default function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [selected, setSelected] = useState<Ticket | null>(null)
  const [events, setEvents] = useState<TicketEvent[]>([])
  const [learnings, setLearnings] = useState<Learning[]>([])

  const refreshTickets = useCallback(async () => {
    setTickets(await api.listTickets())
  }, [])

  const refreshSelected = useCallback(async (ticketId: string) => {
    const [ticket, learningList] = await Promise.all([
      api.getTicket(ticketId),
      api.listLearnings(),
    ])
    setSelected(ticket)
    setLearnings(learningList)
  }, [])

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null))
    refreshTickets().catch(() => undefined)
    api.listLearnings().then(setLearnings).catch(() => undefined)
  }, [refreshTickets])

  useEffect(() => {
    if (!selectedId) return
    let cancelled = false
    setEvents([])
    api.listEvents(selectedId).then((initial) => {
      if (!cancelled) setEvents(initial)
    })
    refreshSelected(selectedId).catch(() => undefined)

    const close = streamTicket(selectedId, (event) => {
      setEvents((current) =>
        current.some((existing) => existing.id === event.id) ? current : [...current, event],
      )
      refreshSelected(selectedId).catch(() => undefined)
      refreshTickets().catch(() => undefined)
    })
    return () => {
      cancelled = true
      close()
    }
  }, [selectedId, refreshSelected, refreshTickets])

  async function createTicket(payload: NewTicket) {
    const ticket = await api.createTicket(payload)
    await refreshTickets()
    setSelectedId(ticket.id)
  }

  async function sendFeedback(subtaskId: string, feedback: string) {
    if (!selectedId) return
    await api.sendFeedback(selectedId, subtaskId, feedback)
  }

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <h1>Ticket → Agents → PR</h1>
          <p className="muted">
            Describe a change; a planner, implementers and a reviewer agent deliver it and the
            pipeline learns from every review round.
          </p>
        </div>
        <div className="health">
          {health ? (
            <>
              <span className={`pill pill-${health.executor}`}>executor: {health.executor}</span>
              <span className="muted">
                {health.devin_configured ? 'Devin API key configured' : 'no Devin API key'} · max{' '}
                {health.max_iterations} review rounds
              </span>
            </>
          ) : (
            <span className="pill pill-failed">backend unreachable</span>
          )}
        </div>
      </header>

      <main className="layout">
        <aside className="sidebar">
          <TicketForm onSubmit={createTicket} disabled={!health} />

          <div className="card">
            <h2>Tickets</h2>
            {tickets.length === 0 && <p className="muted">Nothing submitted yet.</p>}
            <ul className="ticket-list">
              {tickets.map((ticket) => (
                <li key={ticket.id}>
                  <button
                    type="button"
                    className={ticket.id === selectedId ? 'active' : ''}
                    onClick={() => setSelectedId(ticket.id)}
                  >
                    <span className={`pill pill-${ticket.status}`}>
                      {ticket.status.replace(/_/g, ' ')}
                    </span>
                    <strong>{ticket.title}</strong>
                    <span className="muted">{ticket.repo}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>

          <div className="card">
            <h2>What the pipeline learned</h2>
            {learnings.length === 0 ? (
              <p className="muted">Learnings appear after the first retrospective.</p>
            ) : (
              <ul className="learnings">
                {learnings.map((learning) => (
                  <li key={learning.id}>
                    <span className={`pill pill-${learning.kind}`}>{learning.kind}</span>
                    <strong>{learning.title}</strong>
                    <span className="muted">seen {learning.hits}×</span>
                    <p className="detail">{learning.body}</p>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </aside>

        {selected ? (
          <TicketDetail ticket={selected} events={events} onFeedback={sendFeedback} />
        ) : (
          <section className="detail empty">
            <div className="card">
              <h2>Pick a ticket</h2>
              <p className="muted">
                Submit a ticket to watch the planner split it up, implementers open pull requests,
                and the reviewer agent send them back until the acceptance criteria are met.
              </p>
            </div>
          </section>
        )}
      </main>
    </div>
  )
}
