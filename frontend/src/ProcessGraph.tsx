import { useMemo, useState } from "react";
import { EDGES, GROUPS, NODES, RACES, type GraphNode, type MockStatus } from "./processGraphMock";
import { Thumb } from "./ProcessGraphThumbs";
import "./process-graph.css";

const COL_W = 292;
const ROW_H = 186;
const NODE_W = 232;
const NODE_H = 158;
const PAD_X = 36;
const PAD_Y = 70;

const nodeX = (node: GraphNode) => PAD_X + node.col * COL_W;
const nodeY = (node: GraphNode) => PAD_Y + node.lane * ROW_H;

const STATUS_LABEL: Record<MockStatus, string> = {
  PLANNED: "Queued",
  RUNNING: "Running",
  COMPLETED: "Done",
  FAILED: "Failed",
  BLOCKED: "Blocked",
  SKIPPED: "Stopped",
};

const COLUMN_LABELS = [
  "Request",
  "Plan",
  "Gather",
  "Derive",
  "Rank",
  "Probe",
  "Report",
];

export function ProcessGraph() {
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const byId = useMemo(() => new Map(NODES.map((node) => [node.id, node])), []);

  // Highlight the full lineage of the selected node — what led into it and
  // what depends on it — so a single branch reads clearly out of the fan-out.
  const lineage = useMemo(() => {
    if (!selectedId) return null;
    const up = new Set<string>();
    const down = new Set<string>();
    const walk = (id: string, dir: "up" | "down", seen: Set<string>) => {
      for (const edge of EDGES) {
        const next = dir === "up" ? (edge.to === id ? edge.from : null) : edge.from === id ? edge.to : null;
        if (!next || seen.has(next)) continue;
        seen.add(next);
        walk(next, dir, seen);
      }
    };
    walk(selectedId, "up", up);
    walk(selectedId, "down", down);
    return new Set([...up, ...down, selectedId]);
  }, [selectedId]);

  const maxLane = Math.max(...NODES.map((node) => node.lane));
  const maxCol = Math.max(...NODES.map((node) => node.col));
  const width = PAD_X * 2 + maxCol * COL_W + NODE_W;
  const height = PAD_Y * 2 + maxLane * ROW_H + NODE_H + 26;

  const selected = selectedId ? byId.get(selectedId) : null;

  return (
    <section className="pg" aria-label="Investigation process graph">
      <header className="pg-head">
        <div>
          <p className="pg-eyebrow">Investigation graph · mock data</p>
          <h2>Raise IsPETase activity at 50 °C</h2>
        </div>
        <ul className="pg-legend">
          {(["RUNNING", "COMPLETED", "FAILED", "SKIPPED", "PLANNED"] as MockStatus[]).map((status) => (
            <li key={status}>
              <span className={`pg-dot status-${status.toLowerCase()}`} />
              {STATUS_LABEL[status]}
            </li>
          ))}
        </ul>
      </header>

      <div className="pg-scroll">
        <div className="pg-canvas" style={{ width, height }}>
          <div className="pg-columns" aria-hidden>
            {COLUMN_LABELS.map((label, col) => (
              <span key={label} className="pg-col-label" style={{ left: PAD_X + col * COL_W, width: NODE_W }}>
                {label}
              </span>
            ))}
          </div>

          {GROUPS.map((group) => {
            const members = NODES.filter((node) => node.parallelGroup === group.id);
            if (!members.length) return null;
            const top = Math.min(...members.map(nodeY));
            const bottom = Math.max(...members.map(nodeY)) + NODE_H;
            return (
              <div
                key={group.id}
                className="pg-group"
                style={{
                  left: PAD_X + group.col * COL_W - 14,
                  top: top - 18,
                  width: NODE_W + 28,
                  height: bottom - top + 32,
                }}
              >
                <span className="pg-group-tag">{group.label}</span>
              </div>
            );
          })}

          {RACES.map((race) => {
            const members = NODES.filter((node) => node.raceGroup === race.id);
            if (!members.length) return null;
            const top = Math.min(...members.map(nodeY));
            const bottom = Math.max(...members.map(nodeY)) + NODE_H;
            return (
              <div
                key={race.id}
                className="pg-race"
                style={{
                  left: PAD_X + race.col * COL_W - 6,
                  top: top - 8,
                  width: NODE_W + 12,
                  height: bottom - top + 16,
                }}
              >
                <span className="pg-race-tag">
                  <b>{race.label}</b>
                  <em>{race.rule}</em>
                </span>
              </div>
            );
          })}

          <svg className="pg-edges" width={width} height={height} aria-hidden>
            {EDGES.map((edge) => {
              const from = byId.get(edge.from);
              const to = byId.get(edge.to);
              if (!from || !to) return null;
              const x1 = nodeX(from) + NODE_W;
              const y1 = nodeY(from) + NODE_H / 2;
              const x2 = nodeX(to);
              const y2 = nodeY(to) + NODE_H / 2;
              const bend = Math.max(36, (x2 - x1) * 0.5);
              const lit = !!lineage && lineage.has(edge.from) && lineage.has(edge.to);
              const inert =
                to.status === "SKIPPED" ||
                to.status === "PLANNED" ||
                from.status === "FAILED" ||
                to.outcome === "pruned";
              return (
                <path
                  key={`${edge.from}-${edge.to}`}
                  d={`M${x1} ${y1} C ${x1 + bend} ${y1}, ${x2 - bend} ${y2}, ${x2} ${y2}`}
                  className={`pg-edge ${lit ? "is-lit" : ""} ${inert ? "is-inert" : ""}`}
                />
              );
            })}
          </svg>

          {NODES.map((node) => {
            const dimmed = !!lineage && !lineage.has(node.id);
            return (
              <button
                type="button"
                key={node.id}
                className={`pg-node status-${node.status.toLowerCase()} ${node.outcome ? `outcome-${node.outcome}` : ""} ${node.id === selectedId ? "is-selected" : ""} ${dimmed ? "is-dimmed" : ""}`}
                style={{ left: nodeX(node), top: nodeY(node), width: NODE_W, height: NODE_H }}
                onClick={() => setSelectedId((current) => (current === node.id ? null : node.id))}
                aria-pressed={node.id === selectedId}
              >
                <span className="pg-node-top">
                  <span className="pg-cap">{node.capability}</span>
                  <span className="pg-status">
                    {node.status === "RUNNING" ? <span className="pg-pulse" /> : null}
                    {STATUS_LABEL[node.status]}
                  </span>
                </span>

                <strong className="pg-title">{node.title}</strong>

                <span className="pg-body">
                  {node.thumb !== "none" ? (
                    <span className="pg-thumb">
                      <Thumb kind={node.thumb} variant={node.thumbVariant} />
                    </span>
                  ) : node.note ? (
                    <span className="pg-note">{node.note}</span>
                  ) : (
                    <span className="pg-methods">
                      {node.methods.map((method) => (
                        <em key={method}>{method}</em>
                      ))}
                    </span>
                  )}
                </span>

                {node.test ? (
                  <span className={`pg-test ${node.test.passed ? "is-pass" : "is-fail"}`}>
                    {node.test.passed ? "✓" : "✕"} {node.test.label}
                  </span>
                ) : node.metric ? (
                  <span className="pg-metric">
                    {node.outcome ? (
                      <span className={`pg-outcome is-${node.outcome}`}>
                        {node.outcome === "kept" ? "✓ kept" : "✕ discarded"}
                      </span>
                    ) : (
                      <em>{node.metric.label}</em>
                    )}
                    <b>{node.metric.value}</b>
                  </span>
                ) : (
                  <span className="pg-metric pg-metric-empty">
                    <em>no output</em>
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {!selected ? (
        <aside className="pg-inspect pg-inspect-idle">
          <p>Select any task to trace its lineage through the graph.</p>
        </aside>
      ) : (
        <aside className="pg-inspect">
          <div>
            <p className="pg-eyebrow">{selected.capability}</p>
            <h3>{selected.title}</h3>
          </div>
          <dl>
            <div>
              <dt>Status</dt>
              <dd>{STATUS_LABEL[selected.status]}</dd>
            </div>
            {selected.outcome ? (
              <div>
                <dt>Race</dt>
                <dd>{selected.outcome === "kept" ? "Winner — kept" : "Discarded"}</dd>
              </div>
            ) : null}
            <div>
              <dt>Methods</dt>
              <dd>{selected.methods.join(" · ")}</dd>
            </div>
            {selected.metric ? (
              <div>
                <dt>{selected.metric.label}</dt>
                <dd>{selected.metric.value}</dd>
              </div>
            ) : null}
          </dl>
          {selected.note ? <p className="pg-inspect-note">{selected.note}</p> : null}
        </aside>
      )}
    </section>
  );
}
