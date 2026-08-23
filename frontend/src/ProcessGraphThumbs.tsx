import type { ReactNode } from "react";
// Generated preview images for graph nodes. Everything is inline SVG so the
// mockup carries no binary assets; swap these for real render output later.

function rng(seed: number) {
  let s = seed;
  return () => {
    s = (s * 1664525 + 1013904223) % 4294967296;
    return s / 4294967296;
  };
}

const BOX = { w: 200, h: 92 };

function Frame({ children, dim }: { children: ReactNode; dim?: boolean }) {
  return (
    <svg
      className={`pg-thumb-svg ${dim ? "is-dim" : ""}`}
      viewBox={`0 0 ${BOX.w} ${BOX.h}`}
      preserveAspectRatio="xMidYMid slice"
      role="presentation"
    >
      {children}
    </svg>
  );
}

/** AlphaFold-style ribbon, coloured by the canonical pLDDT palette.
 *  `variant` distinguishes competing runs: 0 is a confident fold, 2 is the
 *  low-confidence one that gets pruned. */
function FoldThumb({ variant = 0 }: { variant?: number }) {
  const PALETTES = [
    ["#0053d6", "#0053d6", "#65cbf3", "#0053d6", "#65cbf3"],
    ["#65cbf3", "#0053d6", "#ffdb13", "#65cbf3", "#ffdb13"],
    ["#ffdb13", "#ff7d45", "#ffdb13", "#ff7d45", "#ff7d45"],
  ];
  const palette = PALETTES[Math.min(variant, PALETTES.length - 1)];
  const next = rng([5, 19, 41][Math.min(variant, 2)]);
  const count = palette.length;

  // Spread control points across the box, then join them with quadratic
  // curves whose control point is pushed off the chord — reads as a ribbon.
  const pts = Array.from({ length: count + 1 }, (_, i) => {
    const x = 12 + (i / count) * (BOX.w - 24);
    const y = 22 + next() * 48;
    return [x, y] as const;
  });

  const segments = pts.slice(0, -1).map(([x, y], i) => {
    const [nx, ny] = pts[i + 1];
    const mx = (x + nx) / 2;
    const my = (y + ny) / 2 + (next() - 0.5) * 58;
    return { d: `M${x.toFixed(1)} ${y.toFixed(1)} Q ${mx.toFixed(1)} ${my.toFixed(1)}, ${nx.toFixed(1)} ${ny.toFixed(1)}`, c: palette[i] };
  });

  return (
    <Frame>
      <rect width={BOX.w} height={BOX.h} fill="#f4f8f6" />
      {segments.map((seg) => (
        <path
          key={seg.d}
          d={seg.d}
          fill="none"
          stroke={seg.c}
          strokeWidth={8}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      ))}
    </Frame>
  );
}

/** Per-residue confidence trace over pLDDT confidence bands. */
function PlddtThumb() {
  const next = rng(7);
  const points: string[] = [];
  let value = 78;
  for (let i = 0; i <= 48; i += 1) {
    value += (next() - 0.5) * 16;
    value = Math.max(42, Math.min(97, value));
    const x = (i / 48) * BOX.w;
    const y = BOX.h - ((value - 35) / 65) * BOX.h;
    points.push(`${x.toFixed(1)},${y.toFixed(1)}`);
  }
  const bands = [
    { from: 90, to: 100, c: "#0053d6" },
    { from: 70, to: 90, c: "#65cbf3" },
    { from: 50, to: 70, c: "#ffdb13" },
    { from: 35, to: 50, c: "#ff7d45" },
  ];
  const bandY = (v: number) => BOX.h - ((v - 35) / 65) * BOX.h;
  return (
    <Frame>
      <rect width={BOX.w} height={BOX.h} fill="#f4f8f6" />
      {bands.map((band) => (
        <rect
          key={band.c}
          x={0}
          y={bandY(band.to)}
          width={BOX.w}
          height={bandY(band.from) - bandY(band.to)}
          fill={band.c}
          opacity={0.16}
        />
      ))}
      <polyline
        points={points.join(" ")}
        fill="none"
        stroke="#16241f"
        strokeWidth={2}
        strokeLinejoin="round"
        opacity={0.75}
      />
    </Frame>
  );
}

/** Conservation strip; the tallest columns are the candidate positions. */
function ConservationThumb() {
  const next = rng(21);
  const count = 46;
  const bars = Array.from({ length: count }, () => next());
  const peaks = new Set([9, 17, 28, 39]);
  const w = BOX.w / count;
  return (
    <Frame>
      <rect width={BOX.w} height={BOX.h} fill="#f4f8f6" />
      {bars.map((raw, i) => {
        const value = peaks.has(i) ? 0.82 + raw * 0.18 : raw * 0.72;
        const h = value * (BOX.h - 12);
        return (
          <rect
            key={i}
            x={i * w + 1}
            y={BOX.h - h}
            width={w - 2}
            height={h}
            rx={1}
            fill={peaks.has(i) ? "#056353" : "#087a68"}
            opacity={peaks.has(i) ? 1 : 0.28 + value * 0.4}
          />
        );
      })}
      {[...peaks].map((i) => (
        <circle key={i} cx={i * w + w / 2} cy={5} r={2.4} fill="#b54737" />
      ))}
    </Frame>
  );
}

/** Residue contact map. */
function ContactThumb() {
  const next = rng(33);
  const n = 22;
  const cell = BOX.h / n;
  const offset = (BOX.w - BOX.h) / 2;
  const dots: ReactNode[] = [];
  for (let i = 0; i < n; i += 1) {
    for (let j = 0; j <= i; j += 1) {
      const near = Math.abs(i - j) <= 1;
      const hit = near || next() > 0.86;
      if (!hit) continue;
      const opacity = near ? 0.9 : 0.45;
      dots.push(
        <rect key={`${i}-${j}`} x={offset + j * cell} y={i * cell} width={cell - 0.6} height={cell - 0.6} fill="#087a68" opacity={opacity} />,
        <rect key={`${j}-${i}`} x={offset + i * cell} y={j * cell} width={cell - 0.6} height={cell - 0.6} fill="#087a68" opacity={opacity} />,
      );
    }
  }
  return (
    <Frame>
      <rect width={BOX.w} height={BOX.h} fill="#f4f8f6" />
      {dots}
    </Frame>
  );
}

/** Backbone RMSD across three replicas, truncated at the live frontier. */
function MdThumb() {
  const traces = [12, 44, 91].map((seed, index) => {
    const next = rng(seed);
    const cut = index === 2 ? 0.62 : 0.62;
    const points: string[] = [];
    let value = 0.2;
    for (let i = 0; i <= 60; i += 1) {
      if (i / 60 > cut) break;
      const plateau = 1.6 + index * 0.25;
      value += (plateau - value) * 0.09 + (next() - 0.5) * 0.16;
      const x = (i / 60) * BOX.w;
      const y = BOX.h - (Math.max(0, value) / 2.6) * (BOX.h - 8) - 4;
      points.push(`${x.toFixed(1)},${y.toFixed(1)}`);
    }
    return { points: points.join(" "), opacity: 0.9 - index * 0.22 };
  });
  const frontier = BOX.w * 0.62;
  return (
    <Frame>
      <rect width={BOX.w} height={BOX.h} fill="#f4f8f6" />
      {traces.map((trace) => (
        <polyline
          key={trace.points.slice(0, 12)}
          points={trace.points}
          fill="none"
          stroke="#087a68"
          strokeWidth={1.8}
          strokeLinejoin="round"
          opacity={trace.opacity}
        />
      ))}
      <rect x={frontier} y={0} width={BOX.w - frontier} height={BOX.h} fill="#ffffff" opacity={0.55} />
      <line x1={frontier} y1={0} x2={frontier} y2={BOX.h} stroke="#087a68" strokeWidth={1.5} strokeDasharray="3 3" />
    </Frame>
  );
}

/** Binding pocket with a docked pose — rendered flat because the run stopped. */
function DockingThumb() {
  return (
    <Frame dim>
      <rect width={BOX.w} height={BOX.h} fill="#f4f8f6" />
      <path
        d="M42 20 Q 96 4 152 22 Q 178 44 154 72 Q 98 92 44 70 Q 20 44 42 20 Z"
        fill="none"
        stroke="#66746f"
        strokeWidth={2}
        strokeDasharray="5 4"
      />
      {[
        [84, 42],
        [100, 34],
        [116, 44],
        [110, 60],
        [92, 60],
      ].map(([cx, cy], i, all) => {
        const [nx, ny] = all[(i + 1) % all.length];
        return (
          <g key={`${cx}-${cy}`}>
            <line x1={cx} y1={cy} x2={nx} y2={ny} stroke="#8e9a96" strokeWidth={2} />
            <circle cx={cx} cy={cy} r={4} fill="#8e9a96" />
          </g>
        );
      })}
    </Frame>
  );
}

export function Thumb({ kind, variant }: { kind: string; variant?: number }) {
  if (kind === "fold") return <FoldThumb variant={variant} />;
  if (kind === "plddt") return <PlddtThumb />;
  if (kind === "conservation") return <ConservationThumb />;
  if (kind === "contact") return <ContactThumb />;
  if (kind === "md") return <MdThumb />;
  if (kind === "docking") return <DockingThumb />;
  return null;
}
