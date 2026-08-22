import { useState } from 'react'
import type { Subtask, Ticket, TicketEvent } from '../types'
import { Timeline } from './Timeline'

interface Props {
  ticket: Ticket
  events: TicketEvent[]
  onFeedback: (subtaskId: string, feedback: string) => Promise<void>
}

function SubtaskCard({
  subtask,
  onFeedback,
}: {
  subtask: Subtask
  onFeedback: (subtaskId: string, feedback: string) => Promise<void>
}) {
  const [feedback, setFeedback] = useState('')
  const [busy, setBusy] = useState(false)

  async function send() {
    if (feedback.trim().length < 3) return
    setBusy(true)
    try {
      await onFeedback(subtask.id, feedback.trim())
      setFeedback('')
    } finally {
      setBusy(false)
    }
  }

  return (
    <li className="subtask">
      <div className="subtask-head">
        <span className={`pill pill-${subtask.status}`}>{subtask.status.replace(/_/g, ' ')}</span>
        <strong>{subtask.title}</strong>
        <span className="muted">
          {subtask.iterations} review round{subtask.iterations === 1 ? '' : 's'}
        </span>
      </div>
      <p className="muted">{subtask.description}</p>
      {subtask.acceptance_criteria.length > 0 && (
        <ul className="criteria">
          {subtask.acceptance_criteria.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}
      <div className="links">
        {subtask.pr_url && (
          <a href={subtask.pr_url} target="_blank" rel="noreferrer">
            Pull request →
          </a>
        )}
        {subtask.session_url && (
          <a href={subtask.session_url} target="_blank" rel="noreferrer">
            Devin session →
          </a>
        )}
      </div>
      {subtask.status === 'needs_human' && (
        <div className="feedback">
          <textarea
            rows={2}
            value={feedback}
            placeholder="Tell the implementer what to change, then it re-enters review."
            onChange={(event) => setFeedback(event.target.value)}
          />
          <button type="button" onClick={send} disabled={busy}>
            {busy ? 'Sending…' : 'Send feedback'}
          </button>
        </div>
      )}
    </li>
  )
}

export function TicketDetail({ ticket, events, onFeedback }: Props) {
  return (
    <section className="detail">
      <header className="card">
        <div className="detail-head">
          <h2>{ticket.title}</h2>
          <span className={`pill pill-${ticket.status}`}>
            {ticket.status.replace(/_/g, ' ')}
          </span>
        </div>
        <p className="muted">
          {ticket.repo} · {ticket.base_branch} · max {ticket.max_iterations} review rounds
        </p>
        <p>{ticket.description}</p>
        {ticket.plan?.summary && (
          <p className="plan">
            <strong>Plan:</strong> {ticket.plan.summary}
            {typeof ticket.plan.learnings_applied === 'number' && (
              <span className="muted"> ({ticket.plan.learnings_applied} prior learnings applied)</span>
            )}
          </p>
        )}
        {Object.keys(ticket.metrics).length > 0 && (
          <div className="metrics">
            {Object.entries(ticket.metrics).map(([key, value]) => (
              <span key={key} className="metric">
                <em>{key.replace(/_/g, ' ')}</em>
                <b>{String(value)}</b>
              </span>
            ))}
          </div>
        )}
      </header>

      <div className="card">
        <h3>Subtasks</h3>
        {ticket.subtasks.length === 0 ? (
          <p className="muted">Planner has not produced subtasks yet.</p>
        ) : (
          <ul className="subtasks">
            {ticket.subtasks.map((subtask) => (
              <SubtaskCard key={subtask.id} subtask={subtask} onFeedback={onFeedback} />
            ))}
          </ul>
        )}
      </div>

      <div className="card">
        <h3>Agent activity</h3>
        <Timeline events={events} />
      </div>

      {ticket.retro && (
        <div className="card">
          <h3>Retrospective</h3>
          <p>{ticket.retro.summary}</p>
          {(ticket.retro.recurring_issues ?? []).length > 0 && (
            <ul className="criteria">
              {ticket.retro.recurring_issues?.map((issue) => <li key={issue}>{issue}</li>)}
            </ul>
          )}
          {(ticket.retro.learnings ?? []).map((learning) => (
            <p key={learning.title} className="detail">
              <strong>[{learning.kind}]</strong> {learning.title}: {learning.body}
            </p>
          ))}
        </div>
      )}
    </section>
  )
}
