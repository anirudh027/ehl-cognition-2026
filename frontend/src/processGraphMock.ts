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

export type GraphNode = {
  id: string;
  col: number;
  /** Vertical lane; fractional values are allowed for optical centring. */
  lane: number;
  title: string;
  capability: string;
  status: MockStatus;
  thumb: ThumbKind;
  methods: string[];
  metric?: { label: string; value: string };
  note?: string;
  /** Present when the node is a control / validation run rather than a step. */
  test?: { label: string; passed: boolean };
  parallelGroup?: string;
};

export type GraphEdge = { from: string; to: string };

export type ParallelGroup = { id: string; col: number; label: string };

export const NODES: GraphNode[] = [
  {
    id: "objective",
    col: 0,
    lane: 1.5,
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
    lane: 1.5,
    title: "Plan the investigation",
    capability: "planner",
    status: "COMPLETED",
    thumb: "none",
    methods: ["protein_engineering_v2"],
    metric: { label: "tasks", value: "9 planned" },
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
  {
    id: "fold",
    col: 2,
    lane: 1,
    title: "Predict structure",
    capability: "structure",
    status: "COMPLETED",
    thumb: "fold",
    methods: ["AlphaFold2", "5 models"],
    metric: { label: "mean pLDDT", value: "91.4" },
    parallelGroup: "fan-1",
  },
  {
    id: "literature",
    col: 2,
    lane: 2,
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
    lane: 3,
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
    lane: 1,
    title: "Confidence & burial",
    capability: "structure",
    status: "COMPLETED",
    thumb: "plddt",
    methods: ["DSSP", "per-residue RSA"],
    metric: { label: "buried", value: "141 residues" },
  },
  {
    id: "claims",
    col: 3,
    lane: 2,
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
    lane: 0.5,
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
    lane: 2.2,
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
    lane: 0,
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
    lane: 1.2,
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
    lane: 2.4,
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
    lane: 1.2,
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
  { from: "plan", to: "fold" },
  { from: "plan", to: "literature" },
  { from: "plan", to: "foldseek" },
  { from: "homologs", to: "conservation" },
  { from: "fold", to: "burial" },
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
  { id: "fan-1", col: 2, label: "4 tasks in parallel" },
  { id: "fan-2", col: 5, label: "3 tasks in parallel" },
];
