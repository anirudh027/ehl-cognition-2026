// Static mock data for the sideways process graph.
// Shapes mirror `ResearchTask` in ./types so this can be swapped for live
// job data later without reworking the view.

export type MockStatus =
  | "PLANNED"
  | "RUNNING"
  | "COMPLETED"
  | "FAILED"
  | "BLOCKED"
  | "SKIPPED";

export type ThumbKind =
  | "fold"
  | "plddt"
  | "conservation"
  | "contact"
  | "md"
  | "docking"
  | "none";

/** Result of a race between sibling attempts at the same task. */
export type RaceOutcome = "kept" | "pruned";

export type GraphNode = {
  id: string;
  col: number;
  /** Vertical lane; fractional values are allowed for optical centring. */
  lane: number;
  title: string;
  capability: string;
  status: MockStatus;
  thumb: ThumbKind;
  /** Distinguishes generated previews between sibling runs. */
  thumbVariant?: number;
  methods: string[];
  metric?: { label: string; value: string };
  note?: string;
  /** Present when the node is a control / validation run rather than a step. */
  test?: { label: string; passed: boolean };
  /** Several independent tasks running at the same time. */
  parallelGroup?: string;
  /** Several attempts at the SAME task, competing; only the winner is kept. */
  raceGroup?: string;
  outcome?: RaceOutcome;
};

export type GraphEdge = { from: string; to: string };

export type ParallelGroup = { id: string; col: number; label: string };

/** A cluster of competing attempts, drawn as a bracket inside its column. */
export type RaceGroup = { id: string; col: number; label: string; rule: string };

export const NODES: GraphNode[] = [
  {
    id: "objective",
    col: 0,
    lane: 2.5,
    title: "Raise IsPETase activity at 50 °C",
    capability: "request",
    status: "COMPLETED",
    thumb: "none",
    methods: ["operator brief"],
    metric: { label: "target", value: "PETase / PET hydrolysis" },
  },
  {
    id: "plan",
    col: 1,
    lane: 2.5,
    title: "Plan the investigation",
    capability: "planner",
    status: "COMPLETED",
    thumb: "none",
    methods: ["protein_engineering_v2"],
    metric: { label: "tasks", value: "11 planned" },
  },

  {
    id: "homologs",
    col: 2,
    lane: 0,
    title: "Search homologs",
    capability: "sequence",
    status: "COMPLETED",
    thumb: "none",
    methods: ["jackhmmer", "UniRef90"],
    metric: { label: "hits", value: "412 @ e<1e-5" },
    parallelGroup: "fan-1",
  },

  // --- three competing structure predictions -------------------------------
  {
    id: "fold-a",
    col: 2,
    lane: 1,
    title: "Predict structure · run 1",
    capability: "structure",
    status: "COMPLETED",
    thumb: "fold",
    thumbVariant: 0,
    methods: ["AlphaFold2", "seed 1", "full MSA"],
    metric: { label: "mean pLDDT", value: "91.4" },
    parallelGroup: "fan-1",
    raceGroup: "fold-race",
    outcome: "kept",
  },
  {
    id: "fold-b",
    col: 2,
    lane: 2,
    title: "Predict structure · run 2",
    capability: "structure",
    status: "COMPLETED",
    thumb: "fold",
    thumbVariant: 1,
    methods: ["AlphaFold2", "seed 2", "shallow MSA"],
    metric: { label: "mean pLDDT", value: "74.2" },
    note: "Finished, but 17.2 pLDDT below run 1 — discarded after the race.",
    parallelGroup: "fan-1",
    raceGroup: "fold-race",
    outcome: "pruned",
  },
  {
    id: "fold-c",
    col: 2,
    lane: 3,
    title: "Predict structure · run 3",
    capability: "structure",
    status: "SKIPPED",
    thumb: "fold",
    thumbVariant: 2,
    methods: ["ESMFold", "single sequence"],
    metric: { label: "pLDDT @ stop", value: "58.9" },
    note: "Killed at 41% — pLDDT plateaued under the 70 floor, so compute was released to run 1.",
    parallelGroup: "fan-1",
    raceGroup: "fold-race",
    outcome: "pruned",
  },
  // -------------------------------------------------------------------------

  {
    id: "literature",
    col: 2,
    lane: 4,
    title: "Scan literature",
    capability: "literature",
    status: "COMPLETED",
    thumb: "none",
    methods: ["PubMed", "EuropePMC"],
    metric: { label: "papers", value: "38 screened" },
    parallelGroup: "fan-1",
  },
  {
    id: "foldseek",
    col: 2,
    lane: 5,
    title: "Remote fold search",
    capability: "structure",
    status: "FAILED",
    thumb: "none",
    methods: ["Foldseek", "PDB100"],
    note: "Upstream API returned 503 after 3 retries — branch abandoned.",
    parallelGroup: "fan-1",
  },

  {
    id: "conservation",
    col: 3,
    lane: 0,
    title: "Compute conservation",
    capability: "sequence",
    status: "COMPLETED",
    thumb: "conservation",
    methods: ["MAFFT", "Shannon entropy"],
    metric: { label: "informative", value: "268 columns" },
  },
  {
    id: "burial",
    col: 3,
    lane: 1.6,
    title: "Confidence & burial",
    capability: "structure",
    status: "COMPLETED",
    thumb: "plddt",
    methods: ["DSSP", "per-residue RSA"],
    metric: { label: "buried", value: "141 residues" },
    note: "Runs on the winning fold only.",
  },
  {
    id: "claims",
    col: 3,
    lane: 4,
    title: "Extract prior claims",
    capability: "literature",
    status: "COMPLETED",
    thumb: "none",
    methods: ["claim mining"],
    metric: { label: "claims", value: "17 with DOI" },
  },

  {
    id: "ranking",
    col: 4,
    lane: 1,
    title: "Rank candidate sites",
    capability: "design",
    status: "COMPLETED",
    thumb: "contact",
    methods: ["consensus scoring"],
    metric: { label: "shortlist", value: "12 sites" },
  },
  {
    id: "control",
    col: 4,
    lane: 3.2,
    title: "Scrambled-MSA control",
    capability: "validation",
    status: "COMPLETED",
    thumb: "none",
    methods: ["negative control", "n=200"],
    metric: { label: "signal", value: "0.04 vs 0.61" },
    test: { label: "control passed", passed: true },
  },

  {
    id: "md",
    col: 5,
    lane: 0.4,
    title: "MD stability screen",
    capability: "simulation",
    status: "RUNNING",
    thumb: "md",
    methods: ["OpenMM", "3 × 100 ns"],
    metric: { label: "progress", value: "62 ns / 100 ns" },
    parallelGroup: "fan-2",
  },
  {
    id: "docking",
    col: 5,
    lane: 1.6,
    title: "Docking screen",
    capability: "simulation",
    status: "SKIPPED",
    thumb: "docking",
    methods: ["AutoDock Vina"],
    note: "Stopped before launch — no curated ligand set for PET oligomers.",
    parallelGroup: "fan-2",
  },
  {
    id: "panel",
    col: 5,
    lane: 2.8,
    title: "Mutagenesis panel",
    capability: "design",
    status: "COMPLETED",
    thumb: "none",
    methods: ["saturation design"],
    metric: { label: "variants", value: "6 for assay" },
    parallelGroup: "fan-2",
  },

  {
    id: "synthesis",
    col: 6,
    lane: 1.6,
    title: "Synthesise findings",
    capability: "synthesis",
    status: "PLANNED",
    thumb: "none",
    methods: ["awaiting MD"],
    note: "Blocked until the stability screen finishes.",
  },
];

export const EDGES: GraphEdge[] = [
  { from: "objective", to: "plan" },
  { from: "plan", to: "homologs" },
  { from: "plan", to: "fold-a" },
  { from: "plan", to: "fold-b" },
  { from: "plan", to: "fold-c" },
  { from: "plan", to: "literature" },
  { from: "plan", to: "foldseek" },
  { from: "homologs", to: "conservation" },
  // only the surviving fold feeds downstream work
  { from: "fold-a", to: "burial" },
  { from: "literature", to: "claims" },
  { from: "conservation", to: "ranking" },
  { from: "burial", to: "ranking" },
  { from: "claims", to: "ranking" },
  { from: "conservation", to: "control" },
  { from: "ranking", to: "md" },
  { from: "ranking", to: "docking" },
  { from: "ranking", to: "panel" },
  { from: "md", to: "synthesis" },
  { from: "panel", to: "synthesis" },
];

export const GROUPS: ParallelGroup[] = [
  { id: "fan-1", col: 2, label: "6 tasks in parallel" },
  { id: "fan-2", col: 5, label: "3 tasks in parallel" },
];

export const RACES: RaceGroup[] = [
  {
    id: "fold-race",
    col: 2,
    label: "3 competing runs",
    rule: "keep highest pLDDT · kill below 70",
  },
];
