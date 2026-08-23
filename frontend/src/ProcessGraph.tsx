import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { EDGES, GROUPS, NODES, RACES, type GraphNode, type MockStatus } from "./processGraphMock";
import { StructureViewer } from "./StructureViewer";
import { Thumb } from "./ProcessGraphThumbs";
import "./process-graph.css";

const COL_W = 292;
const ROW_H = 202;
const NODE_W = 232;
const NODE_H = 176;
const ZOOM_MIN = 0.35;
const ZOOM_MAX = 1.8;
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
  const [zoom, setZoom] = useState(1);
  const [panning, setPanning] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const zoomRef = useRef(1);
  // Point of the diagram to hold still while the scale changes.
  const anchorRef = useRef<{ cx: number; cy: number; ax: number; ay: number } | null>(null);
  const panRef = useRef<{ x: number; y: number; sl: number; st: number } | null>(null);

  const applyZoom = useCallback((next: number, clientX?: number, clientY?: number) => {
    const clamped = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, next));
    const el = scrollRef.current;
    if (el) {
      const rect = el.getBoundingClientRect();
      const ax = clientX == null ? el.clientWidth / 2 : clientX - rect.left;
      const ay = clientY == null ? el.clientHeight / 2 : clientY - rect.top;
      anchorRef.current = {
        cx: (el.scrollLeft + ax) / zoomRef.current,
        cy: (el.scrollTop + ay) / zoomRef.current,
        ax,
        ay,
      };
    }
    setZoom(clamped);
  }, []);

  // Restore the anchor point after the browser has laid out the new scale.
  useLayoutEffect(() => {
    zoomRef.current = zoom;
    const el = scrollRef.current;
    const anchor = anchorRef.current;
    if (!el || !anchor) return;
    el.scrollLeft = anchor.cx * zoom - anchor.ax;
    el.scrollTop = anchor.cy * zoom - anchor.ay;
    anchorRef.current = null;
  }, [zoom]);

  // Trackpad pinch and ctrl/cmd + wheel zoom; a plain wheel still scrolls.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onWheel = (event: WheelEvent) => {
      if (!event.ctrlKey && !event.metaKey) return;
      event.preventDefault();
      applyZoom(zoomRef.current * (1 - event.deltaY * 0.0018), event.clientX, event.clientY);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [applyZoom]);


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

  // PDB text is fetched once per file and cached, so re-selecting a
  // structure node does not refetch or restart the viewer needlessly.
  const [pdbText, setPdbText] = useState<string | null>(null);
  const pdbCache = useRef(new Map<string, string>());
  const structureFile = selected?.structure?.file ?? null;

  useEffect(() => {
    if (!structureFile) {
      setPdbText(null);
      return;
    }
    const cached = pdbCache.current.get(structureFile);
    if (cached) {
      setPdbText(cached);
      return;
    }
    let cancelled = false;
    setPdbText(null);
    void fetch(structureFile)
      .then((response) => (response.ok ? response.text() : Promise.reject(new Error(String(response.status)))))
      .then((text) => {
        pdbCache.current.set(structureFile, text);
        if (!cancelled) setPdbText(text);
      })
      .catch(() => {
        if (!cancelled) setPdbText(null);
      });
    return () => {
      cancelled = true;
    };
  }, [structureFile]);

  const fitToView = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const scale = Math.min((el.clientWidth - 24) / width, (el.clientHeight - 24) / height, 1);
    anchorRef.current = { cx: 0, cy: 0, ax: 0, ay: 0 };
    setZoom(Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, scale)));
  }, [height, width]);

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
        <div className="pg-zoom">
          <button type="button" onClick={() => applyZoom(zoom - 0.15)} aria-label="Zoom out" disabled={zoom <= ZOOM_MIN}>
            −
          </button>
          <button type="button" className="pg-zoom-level" onClick={() => applyZoom(1)} title="Reset to 100%">
            {Math.round(zoom * 100)}%
          </button>
          <button type="button" onClick={() => applyZoom(zoom + 0.15)} aria-label="Zoom in" disabled={zoom >= ZOOM_MAX}>
            +
          </button>
          <button type="button" className="pg-zoom-fit" onClick={fitToView}>
            Fit
          </button>
        </div>
      </header>

      <div className="pg-main">
      <div
        className={`pg-scroll ${panning ? "is-panning" : ""}`}
        ref={scrollRef}
        onPointerDown={(event) => {
          // Dragging the background pans; dragging a card must still click it.
          if ((event.target as HTMLElement).closest(".pg-node")) return;
          const el = scrollRef.current;
          if (!el) return;
          panRef.current = { x: event.clientX, y: event.clientY, sl: el.scrollLeft, st: el.scrollTop };
          setPanning(true);
          el.setPointerCapture(event.pointerId);
        }}
        onPointerMove={(event) => {
          const pan = panRef.current;
          const el = scrollRef.current;
          if (!pan || !el) return;
          el.scrollLeft = pan.sl - (event.clientX - pan.x);
          el.scrollTop = pan.st - (event.clientY - pan.y);
        }}
        onPointerUp={(event) => {
          panRef.current = null;
          setPanning(false);
          scrollRef.current?.releasePointerCapture(event.pointerId);
        }}
        onPointerCancel={() => {
          panRef.current = null;
          setPanning(false);
        }}
      >
        <div className="pg-stage" style={{ width: width * zoom, height: height * zoom }}>
        <div className="pg-canvas" style={{ width, height, transform: `scale(${zoom})` }}>
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
                  <span className="pg-cap">
                    {node.taskNumber ? <b className="pg-num">{node.taskNumber}</b> : null}
                    {node.capability}
                  </span>
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
                        {node.outcomeLabel ?? (node.outcome === "kept" ? "✓ kept" : "✕ discarded")}
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

                <span className="pg-foot">
                  <span className="pg-foot-left">
                    {node.outputs?.length ? (
                      <span className="pg-outputs" title={node.outputs.join(", ")}>
                        ◆ {node.outputs.length}
                      </span>
                    ) : null}
                    {node.counterEvidence ? (
                      <span className="pg-counter-flag" title="Counter-evidence recorded">
                        ⚑ counter-evidence
                      </span>
                    ) : null}
                  </span>
                  {node.duration ? <span className="pg-dur">{node.duration}</span> : null}
                </span>
              </button>
            );
          })}
        </div>
        </div>
      </div>

      {!selected ? (
        <aside className="pg-dock pg-dock-idle">
          <p>Select a task to read what it did, what it produced, and what argues against it.</p>
        </aside>
      ) : (
        <aside className="pg-dock">
          <header className="pg-dock-head">
            <p className="pg-eyebrow">
              {selected.taskNumber ? `Task ${selected.taskNumber} · ` : ""}
              {selected.capability}
            </p>
            <h3>{selected.title}</h3>
            <div className="pg-dock-meta">
              <span className={`pg-status status-chip-${selected.status.toLowerCase()}`}>
                {STATUS_LABEL[selected.status]}
              </span>
              {selected.outcomeLabel ? <span className="pg-dock-outcome">{selected.outcomeLabel}</span> : null}
              {selected.duration ? <span className="pg-dur">{selected.duration}</span> : null}
            </div>
          </header>

          <div className="pg-dock-scroll">
            {selected.structure ? (
              <section className="pg-structure">
                <h4>Structure</h4>
                <div className="pg-viewer-host">
                  {pdbText ? (
                    <StructureViewer
                      key={`${selected.id}-${selected.structure.file}`}
                      pdbText={pdbText}
                      triad={selected.structure.triad}
                      activity={selected.structure.activity}
                      stability={selected.structure.stability}
                      focus={selected.structure.focus}
                      overview={selected.structure.overview}
                    />
                  ) : (
                    <p className="pg-viewer-loading">Loading structure…</p>
                  )}
                </div>
                <p className="pg-viewer-caption">{selected.structure.caption}</p>
              </section>
            ) : null}

            {selected.log?.length ? (
              <section>
                <h4>What ran</h4>
                {selected.log.map((line) => (
                  <p key={line}>{line}</p>
                ))}
              </section>
            ) : null}

            {selected.note ? (
              <section>
                <h4>Why it went this way</h4>
                <p>{selected.note}</p>
              </section>
            ) : null}

            {selected.counterEvidence ? (
              <section className="pg-counter">
                <h4>⚑ Counter-evidence</h4>
                <p>{selected.counterEvidence}</p>
              </section>
            ) : null}

            {selected.outputs?.length ? (
              <section>
                <h4>Outputs</h4>
                <div className="pg-chips">
                  {selected.outputs.map((file) => (
                    <span key={file} className="pg-file">
                      {file}
                    </span>
                  ))}
                </div>
              </section>
            ) : null}

            <section>
              <h4>Methods</h4>
              <div className="pg-chips">
                {selected.methods.map((method) => (
                  <span key={method} className="pg-chip">
                    {method}
                  </span>
                ))}
              </div>
            </section>

            {selected.limitations?.length ? (
              <section>
                <h4>Limitations carried downstream</h4>
                <ul className="pg-lims">
                  {selected.limitations.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </section>
            ) : null}
          </div>
        </aside>
      )}
      </div>
    </section>
  );
}
