import type { TicketEvent } from '../types'

const ROLE_LABEL: Record<string, string> = {
  planner: 'Planner',
  implementer: 'Implementer',
  critic: 'Reviewer',
  retrospective: 'Retrospective',
}

function detailLines(event: TicketEvent): string[] {
  const data = event.data
  if (!data) return []
  const lines: string[] = []
  const comments = data.comments
  if (Array.isArray(comments)) lines.push(...comments.map(String))
  const unmet = data.unmet_criteria
  if (Array.isArray(unmet) && unmet.length > 0) {
    lines.push(`Unmet: ${unmet.map(String).join('; ')}`)
  }
  const risks = data.risks
  if (Array.isArray(risks)) lines.push(...risks.map((risk) => `Risk: ${String(risk)}`))
  const issues = data.recurring_issues
  if (Array.isArray(issues)) lines.push(...issues.map((issue) => `Pattern: ${String(issue)}`))
  const files = data.files_changed
  if (Array.isArray(files) && files.length > 0) {
    lines.push(`Files: ${files.map(String).join(', ')}`)
  }
  return lines
}

function linkOf(event: TicketEvent): { label: string; href: string } | null {
  const data = event.data
  if (!data) return null
  if (typeof data.pr_url === 'string') return { label: 'Pull request', href: data.pr_url }
  if (typeof data.session_url === 'string') return { label: 'Devin session', href: data.session_url }
  return null
}

export function Timeline({ events }: { events: TicketEvent[] }) {
  const visible = events.filter((event) => event.phase !== 'status')
  if (visible.length === 0) {
    return <p className="muted">No agent activity yet.</p>
  }
  return (
    <ol className="timeline">
      {visible.map((event) => {
        const link = linkOf(event)
        return (
          <li key={event.id} className={`timeline-item level-${event.level}`}>
            <div className="timeline-head">
              <span className={`role role-${event.role ?? 'system'}`}>
                {ROLE_LABEL[event.role ?? ''] ?? 'Pipeline'}
              </span>
              <span className="phase">{event.phase.replace(/_/g, ' ')}</span>
              <time>{new Date(event.created_at).toLocaleTimeString()}</time>
            </div>
            <p>{event.message}</p>
            {detailLines(event).map((line, index) => (
              <p className="detail" key={index}>
                {line}
              </p>
            ))}
            {link && (
              <a href={link.href} target="_blank" rel="noreferrer">
                {link.label} →
              </a>
            )}
          </li>
        )
      })}
    </ol>
  )
}
