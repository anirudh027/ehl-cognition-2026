import { useState } from 'react'
import type { NewTicket } from '../types'

interface Props {
  onSubmit: (ticket: NewTicket) => Promise<void>
  disabled: boolean
}

const EMPTY = {
  title: '',
  description: '',
  repo: '',
  base_branch: 'main',
  criteria: '',
}

export function TicketForm({ onSubmit, disabled }: Props) {
  const [form, setForm] = useState(EMPTY)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const update = (key: keyof typeof EMPTY) => (value: string) =>
    setForm((current) => ({ ...current, [key]: value }))

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await onSubmit({
        title: form.title.trim(),
        description: form.description.trim(),
        repo: form.repo.trim(),
        base_branch: form.base_branch.trim() || 'main',
        acceptance_criteria: form.criteria
          .split('\n')
          .map((line) => line.trim())
          .filter(Boolean),
      })
      setForm(EMPTY)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="card ticket-form" onSubmit={submit}>
      <h2>New ticket</h2>
      <label>
        Title
        <input
          value={form.title}
          onChange={(event) => update('title')(event.target.value)}
          placeholder="Add CSV export to the reports page"
          required
          minLength={3}
        />
      </label>
      <label>
        Repository
        <input
          value={form.repo}
          onChange={(event) => update('repo')(event.target.value)}
          placeholder="owner/repo"
          required
        />
      </label>
      <label>
        Base branch
        <input
          value={form.base_branch}
          onChange={(event) => update('base_branch')(event.target.value)}
          placeholder="main"
        />
      </label>
      <label>
        What needs to happen
        <textarea
          value={form.description}
          onChange={(event) => update('description')(event.target.value)}
          rows={5}
          placeholder="Describe the change the way you would for a teammate."
          required
          minLength={3}
        />
      </label>
      <label>
        Acceptance criteria (one per line)
        <textarea
          value={form.criteria}
          onChange={(event) => update('criteria')(event.target.value)}
          rows={3}
          placeholder={'A download button exports the current filter set\nTests cover an empty result set'}
        />
      </label>
      {error && <p className="error">{error}</p>}
      <button type="submit" disabled={disabled || busy}>
        {busy ? 'Dispatching agents…' : 'Dispatch agents'}
      </button>
    </form>
  )
}
