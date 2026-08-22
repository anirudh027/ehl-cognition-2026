"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import {
  API_URL,
  artifactUrl,
  createRun,
  getRun,
  refreshTraces,
  sendFollowUp,
} from "@/lib/api";
import type { Agent, AgentTrace, Candidate, Run, RunEvent } from "@/lib/types";

const DEFAULT_OBJECTIVE =
  "Develop a PET-degrading enzyme that remains useful around 60 °C while preserving catalytic function.";

const FOLLOW_UP_EXAMPLE =
  "Exclude mutations within 10 Å of the catalytic site.";
const LAST_RUN_KEY = "catalyst.lastRunId";

function formatTime(value: string): string {
  return new Intl.DateTimeFormat("en", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value));
}

function label(value: string): string {
  return value.replaceAll("_", " ");
}

function statusLabel(value: string): string {
  if (value === "completed") return "Complete";
  if (value === "running") return "Working";
  if (value === "failed") return "Failed";
  return "Queued";
}

function traceSourceLabel(source: string): string {
  if (source === "user") return "Instruction";
  if (source === "devin") return "Devin";
  return label(source);
}

function AgentTraceList({ traces }: { traces: AgentTrace[] }) {
  return (
    <details className="trace-block">
      <summary>Thought trace · {traces.length}</summary>
      <ol className="trace-list">
        {traces.map((trace) => (
          <li key={trace.id} className={`trace-item trace-${trace.source}`}>
            <span className="trace-source">{traceSourceLabel(trace.source)}</span>
            <p>{trace.body}</p>
          </li>
        ))}
      </ol>
    </details>
  );
}

function AgentCard({ agent, child }: { agent: Agent; child?: boolean }) {
  const traces = agent.traces ?? [];
  return (
    <div className={`agent-card ${child ? "agent-child" : ""}`}>
      <div className="agent-identity">
        <span className={`agent-dot status-${agent.status}`} />
        <div>
          <strong>{agent.name}</strong>
          <span>{label(agent.role)}</span>
        </div>
      </div>
      <span className={`status-pill status-${agent.status}`}>
        {statusLabel(agent.status)}
      </span>
      <p>{agent.summary}</p>
      {agent.url ? (
        <div className="managed-agent-meta">
          <a href={agent.url} target="_blank" rel="noreferrer">
            Open Devin session
          </a>
          <span>{agent.acus_consumed.toFixed(2)} ACUs</span>
        </div>
      ) : null}
      {traces.length > 0 ? <AgentTraceList traces={traces} /> : null}
    </div>
  );
}

function TimelineItem({
  event,
  agents,
}: {
  event: RunEvent;
  agents: Agent[];
}) {
  const agent = agents.find((item) => item.id === event.agent_id);
  return (
    <li className={`timeline-item tone-${event.tone}`}>
      <span className="timeline-marker" />
      <div className="timeline-content">
        <div className="timeline-meta">
          <span>{agent?.name ?? "System"}</span>
          <time>{formatTime(event.created_at)}</time>
        </div>
        <strong>{event.title}</strong>
        <p>{event.detail}</p>
      </div>
    </li>
  );
}

function CandidateRow({ candidate, rank }: { candidate: Candidate; rank: number }) {
  return (
    <tr className={candidate.excluded ? "candidate-excluded" : ""}>
      <td>
        <span className="rank">{candidate.excluded ? "—" : rank}</span>
      </td>
      <td>
        <div className="mutation">
          <strong>{candidate.mutation}</strong>
          {candidate.excluded && <span>excluded by follow-up</span>}
        </div>
      </td>
      <td>
        <div className="score">
          <strong>{Math.round(candidate.score * 100)}</strong>
          <div className="score-track">
            <span style={{ width: `${candidate.score * 100}%` }} />
          </div>
        </div>
      </td>
      <td>{candidate.distance.toFixed(1)} Å</td>
      <td>{candidate.conservation.toFixed(2)}</td>
      <td>
        <div className="evidence-list">
          {candidate.evidence.map((item) => (
            <span key={item} className={`evidence evidence-${item.toLowerCase()}`}>
              {item}
            </span>
          ))}
        </div>
      </td>
    </tr>
  );
}

export default function Home() {
  const [objective, setObjective] = useState(DEFAULT_OBJECTIVE);
  const [mode, setMode] = useState<"local" | "devin">("local");
  const [run, setRun] = useState<Run | null>(null);
  const [followUp, setFollowUp] = useState(FOLLOW_UP_EXAMPLE);
  const [isStarting, setIsStarting] = useState(false);
  const [isSteering, setIsSteering] = useState(false);
  const [isLoadingTraces, setIsLoadingTraces] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async (runId: string) => {
    try {
      setRun(await getRun(runId));
      setError(null);
    } catch (refreshError) {
      setError(
        refreshError instanceof Error ? refreshError.message : "Unable to refresh run",
      );
    }
  }, []);

  useEffect(() => {
    const lastRunId = window.localStorage.getItem(LAST_RUN_KEY);
    if (!lastRunId) return;
    const timer = window.setTimeout(() => void refresh(lastRunId), 0);
    return () => window.clearTimeout(timer);
  }, [refresh]);

  useEffect(() => {
    if (run?.id) window.localStorage.setItem(LAST_RUN_KEY, run.id);
  }, [run?.id]);

  useEffect(() => {
    if (!run?.id) return;
    const source = new EventSource(`${API_URL}/api/runs/${run.id}/events`);
    let refreshTimer: ReturnType<typeof setTimeout> | null = null;
    source.addEventListener("run_event", () => {
      if (refreshTimer) clearTimeout(refreshTimer);
      refreshTimer = setTimeout(() => void refresh(run.id), 80);
    });
    source.onerror = () => {
      if (run.status === "running" || run.status === "queued") {
        setError("Live updates paused; reconnecting…");
      }
    };
    return () => {
      if (refreshTimer) clearTimeout(refreshTimer);
      source.close();
    };
  }, [refresh, run?.id, run?.status]);

  const coordinator = run?.agents.find((agent) => agent.role === "coordinator");
  const children = run?.agents.filter((agent) => agent.role !== "coordinator") ?? [];
  const activeCandidates =
    run?.candidates.filter((candidate) => !candidate.excluded) ?? [];
  const sortedCandidates = useMemo(
    () =>
      [...(run?.candidates ?? [])].sort(
        (left, right) =>
          Number(left.excluded) - Number(right.excluded) || right.score - left.score,
      ),
    [run?.candidates],
  );

  async function handleStart(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsStarting(true);
    setError(null);
    try {
      setRun(await createRun(objective.trim(), mode));
    } catch (startError) {
      setError(startError instanceof Error ? startError.message : "Unable to start run");
    } finally {
      setIsStarting(false);
    }
  }

  async function handleLoadTraces() {
    if (!run) return;
    setIsLoadingTraces(true);
    setError(null);
    try {
      setRun(await refreshTraces(run.id));
    } catch (traceError) {
      setError(
        traceError instanceof Error ? traceError.message : "Unable to load session traces",
      );
    } finally {
      setIsLoadingTraces(false);
    }
  }

  async function handleFollowUp(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!run) return;
    setIsSteering(true);
    setError(null);
    try {
      setRun(await sendFollowUp(run.id, followUp.trim()));
      setFollowUp("");
    } catch (steeringError) {
      setError(
        steeringError instanceof Error
          ? steeringError.message
          : "Unable to apply follow-up",
      );
    } finally {
      setIsSteering(false);
    }
  }

  return (
    <main>
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">C</span>
          <div>
            <strong>Catalyst</strong>
            <span>Bioengineering orchestrator</span>
          </div>
        </div>
        <div className="local-badge">
          <span />
          {run?.mode === "devin" ? "Managed Devin · uses ACUs" : "Local scientific demo"}
        </div>
      </header>

      <section className="hero">
        <div>
          <p className="eyebrow">CPU-first protein engineering</p>
          <h1>From objective to an evidence-backed mutation shortlist.</h1>
          <p className="hero-copy">
            A compact orchestration surface for following specialist agents,
            scientific tools, recoveries, artifacts, and human steering.
          </p>
        </div>
        <form className="objective-card" onSubmit={handleStart}>
          <label htmlFor="objective">Engineering objective</label>
          <textarea
            id="objective"
            value={objective}
            onChange={(event) => setObjective(event.target.value)}
            rows={4}
            minLength={12}
            required
          />
          <div className="mode-picker" aria-label="Execution mode">
            <button
              type="button"
              className={mode === "local" ? "active" : ""}
              onClick={() => setMode("local")}
            >
              Local · zero ACUs
            </button>
            <button
              type="button"
              className={mode === "devin" ? "active" : ""}
              onClick={() => setMode("devin")}
            >
              Managed Devin · uses credits
            </button>
          </div>
          <div className="objective-footer">
            <span>
              {mode === "devin"
                ? "Real sessions · server-side credential · per-session ACU cap"
                : "Curated IsPETase demo dataset"}
            </span>
            <button type="submit" disabled={isStarting}>
              {isStarting ? "Starting…" : run ? "Start another run" : "Launch run"}
              <span aria-hidden="true">→</span>
            </button>
          </div>
        </form>
      </section>

      {error && <div className="error-banner">{error}</div>}

      {!run ? (
        <section className="empty-grid">
          <article>
            <span>01</span>
            <h2>Parallel evidence</h2>
            <p>Sequence and structure workers operate independently, then combine.</p>
          </article>
          <article>
            <span>02</span>
            <h2>Visible recovery</h2>
            <p>A real DSSP input failure is diagnosed, repaired, and retried.</p>
          </article>
          <article>
            <span>03</span>
            <h2>Steerable output</h2>
            <p>Follow-up constraints update only the downstream candidate ranking.</p>
          </article>
        </section>
      ) : (
        <section className="dashboard">
          <div className="run-header panel">
            <div>
              <div className="run-kicker">
                <span className={`status-dot status-${run.status}`} />
                Run {run.id} · {run.mode} mode
              </div>
              <h2>{run.stage}</h2>
              <p>{run.objective}</p>
            </div>
            <div className="run-progress">
              <div>
                <strong>{run.progress}%</strong>
                <span>Result v{run.result_version}</span>
              </div>
              <div className="progress-track">
                <span style={{ width: `${run.progress}%` }} />
              </div>
            </div>
          </div>

          <div className="dashboard-grid">
            <aside className="agents-panel panel">
              <div className="panel-heading">
                <div>
                  <p className="eyebrow">Managed work</p>
                  <h2>Agent hierarchy</h2>
                </div>
                <span>{run.agents.length}</span>
              </div>
              {run.mode === "devin" ? (
                <button
                  type="button"
                  className="trace-refresh"
                  onClick={() => void handleLoadTraces()}
                  disabled={isLoadingTraces}
                >
                  {isLoadingTraces ? "Loading traces…" : "Sync session traces"}
                </button>
              ) : null}
              {coordinator && <AgentCard agent={coordinator} />}
              <div className="agent-branch">
                {children.map((agent) => (
                  <AgentCard key={agent.id} agent={agent} child />
                ))}
              </div>
              <div className="guardrail">
                <strong>Scientific guardrail</strong>
                <p>Predictions are never presented as experimental measurements.</p>
              </div>
            </aside>

            <section className="activity-panel panel">
              <div className="panel-heading">
                <div>
                  <p className="eyebrow">Live trace</p>
                  <h2>Investigation activity</h2>
                </div>
                <span>{run.events.length}</span>
              </div>
              <ol className="timeline">
                {[...run.events].reverse().map((event) => (
                  <TimelineItem key={event.id} event={event} agents={run.agents} />
                ))}
              </ol>
            </section>

            <aside className="evidence-panel panel">
              <div className="panel-heading">
                <div>
                  <p className="eyebrow">Run outputs</p>
                  <h2>Evidence artifacts</h2>
                </div>
                <span>{run.artifacts.length}</span>
              </div>
              <div className="artifact-list">
                {run.artifacts.length === 0 && (
                  <p className="muted">Artifacts will appear as tools complete.</p>
                )}
                {run.artifacts.map((artifact) => (
                  <a
                    key={artifact.id}
                    className="artifact"
                    href={artifactUrl(artifact.id)}
                    target="_blank"
                    rel="noreferrer"
                  >
                    <span className="artifact-icon">{artifact.name.split(".").at(-1)}</span>
                    <span>
                      <strong>{artifact.name}</strong>
                      <small>{artifact.description}</small>
                    </span>
                    <b aria-hidden="true">↗</b>
                  </a>
                ))}
              </div>
              <dl className="run-facts">
                <div>
                  <dt>Target</dt>
                  <dd>IsPETase</dd>
                </div>
                <div>
                  <dt>Structure</dt>
                  <dd>5XJH · 1.54 Å</dd>
                </div>
                <div>
                  <dt>Toolchain</dt>
                  <dd>MAFFT · DSSP · Bio.PDB</dd>
                </div>
              </dl>
            </aside>
          </div>

          <section className="candidates-panel panel">
            <div className="candidate-heading">
              <div>
                <p className="eyebrow">Multi-objective ranking</p>
                <h2>Candidate mutation shortlist</h2>
                <p>
                  {activeCandidates.length
                    ? `${activeCandidates.length} active candidates prioritized for human review.`
                    : "Candidates will appear after evidence is combined."}
                </p>
              </div>
              <div className="evidence-legend">
                <span className="evidence evidence-known">KNOWN</span>
                <span className="evidence evidence-calculated">CALCULATED</span>
                <span className="evidence evidence-predicted">PREDICTED</span>
              </div>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Rank</th>
                    <th>Mutation</th>
                    <th>Priority</th>
                    <th>Active-site distance</th>
                    <th>Conservation</th>
                    <th>Evidence</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedCandidates.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="table-empty">
                        Coordinator is waiting for both evidence tracks.
                      </td>
                    </tr>
                  ) : (
                    sortedCandidates.map((candidate, index) => (
                      <CandidateRow
                        key={candidate.id}
                        candidate={candidate}
                        rank={
                          sortedCandidates
                            .slice(0, index + 1)
                            .filter((item) => !item.excluded).length
                        }
                      />
                    ))
                  )}
                </tbody>
              </table>
            </div>
            {sortedCandidates[0] && (
              <p className="candidate-note">
                <strong>Why {sortedCandidates[0].mutation}:</strong>{" "}
                {sortedCandidates[0].rationale}
              </p>
            )}
          </section>

          <section className="followup-panel panel">
            <div>
              <p className="eyebrow">Human steering</p>
              <h2>Refine this run</h2>
              <p>
                The coordinator reuses completed artifacts and only recomputes the
                affected ranking.
              </p>
            </div>
            <form onSubmit={handleFollowUp}>
              <input
                value={followUp}
                onChange={(event) => setFollowUp(event.target.value)}
                placeholder={FOLLOW_UP_EXAMPLE}
                minLength={3}
                required
                disabled={run.status !== "completed" || isSteering}
              />
              <button
                type="submit"
                disabled={run.status !== "completed" || isSteering}
              >
                {isSteering ? "Applying…" : "Apply constraint"}
              </button>
            </form>
            {run.messages.length > 0 && (
              <div className="message-history">
                {run.messages.map((message) => (
                  <span key={message.id}>{message.body}</span>
                ))}
              </div>
            )}
          </section>
        </section>
      )}

      <footer>
        <span>Local CPU workflow · no experimental claims</span>
        <span>FastAPI + Next.js</span>
      </footer>
    </main>
  );
}
