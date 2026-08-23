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
  /** Overrides the default chip text, e.g. to mark primary vs alternate. */
  outcomeLabel?: string;
  /** Position in the flat task list the operator sees elsewhere. */
  taskNumber?: number;
  /** Wall-clock the task consumed, or has consumed so far. */
  duration?: string;
  /** Clock time the task reported in, for the chronological log. */
  at?: string;
  /** Artifact filenames this task wrote. */
  outputs?: string[];
  /** What the agent actually did, in its own words — the execution log,
   *  split per task rather than one global scroll. */
  log?: string[];
  /** Disconfirming evidence deliberately kept in view. */
  counterEvidence?: string;
  /** Caveats this task attaches to anything downstream of it. */
  limitations?: string[];
  /** A real structure to render, rotating, in the detail dock. */
  structure?: {
    file: string;
    caption: string;
    triad: number[];
    activity: number[];
    stability: number[];
    focus: number | null;
    /** Frame the whole chain instead of zooming to one residue. */
    overview?: boolean;
  };
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
    at: "08:00",
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
    at: "08:02",
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
    taskNumber: 1,
    duration: "6m 12s",
    outputs: ["homolog_search.json"],
    log: [
      "jackhmmer against UniRef90, 3 iterations, gathering to e<1e-5.",
      "412 hits retained after removing fragments under 60% coverage.",
    ],
    at: "08:05",
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
    outcomeLabel: "kept · primary",
    taskNumber: 2,
    duration: "41m 08s",
    outputs: ["fold_run1.pdb", "plddt_run1.json"],
    log: [
      "AlphaFold2 with the full 412-sequence MSA, 5 models, seed 1.",
      "Best model mean pLDDT 91.4; the catalytic triad region scores 94.8, " +
        "so confidence is high exactly where the question is.",
    ],
    structure: {
      file: "/structures/5XJH_A.pdb",
      caption:
        "PETase from Ideonella sakaiensis (PDB 5XJH, chain A). Red is the " +
        "Ser160–Asp206–His237 catalytic triad, teal the activity hotspots, " +
        "blue the stability set.",
      triad: [160, 206, 237],
      activity: [159, 238],
      stability: [121, 186, 280],
      focus: null,
      overview: true,
    },
    at: "08:06",
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
    note:
      "Lower confidence than run 1, but the subsampled MSA settled on an open " +
      "substrate groove — TM-score 0.71 to run 1, so it is a distinct hypothesis " +
      "rather than a worse copy of the same fold. Carried forward.",
    parallelGroup: "fan-1",
    raceGroup: "fold-race",
    outcome: "kept",
    outcomeLabel: "kept · alternate",
    taskNumber: 3,
    duration: "38m 55s",
    outputs: ["fold_run2.pdb"],
    log: [
      "AlphaFold2 with the MSA subsampled to 32 sequences, seed 2 — run " +
        "deliberately to sample alternative conformations rather than to beat run 1.",
      "Converged on an open substrate groove; TM-score 0.71 against run 1.",
    ],
    counterEvidence:
      "TM-score 0.71 sits above the 0.5 fold-identity line, so this is the same " +
      "fold in a different state — but shallow-MSA sampling is known to produce " +
      "plausible-looking states that are artefacts. The open groove is a hypothesis, " +
      "not an observation.",
    limitations: [
      "No experimental structure supports the open state.",
      "Anything ranked only in this conformation inherits its uncertainty.",
    ],
    structure: {
      file: "/structures/5XJH_A.pdb",
      caption:
        "Same chain, framed on the substrate groove that run 2 predicts open. " +
        "Compare the W159/S238 pocket against run 1.",
      triad: [160, 206, 237],
      activity: [159, 238],
      stability: [121, 186, 280],
      focus: 159,
    },
    at: "08:06",
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
    note:
      "Killed at 41% — pLDDT plateaued under the 70 floor. Single-sequence input " +
      "on a target with a deep MSA available, so it was the least-informed run; " +
      "compute was released to the survivors.",
    parallelGroup: "fan-1",
    raceGroup: "fold-race",
    outcome: "pruned",
    taskNumber: 4,
    duration: "12m 30s (killed)",
    log: [
      "ESMFold, single sequence, no MSA.",
      "pLDDT plateaued at 58.9 by residue 190 and stopped climbing; killed at 41% " +
        "and the GPU was handed back to run 1.",
    ],
    at: "08:06",
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
    taskNumber: 5,
    duration: "4m 02s",
    outputs: ["literature.json"],
    log: ["PubMed and EuropePMC, 2019 onward; 38 abstracts screened, 12 read in full."],
    at: "08:06",
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
    taskNumber: 6,
    duration: "0m 38s",
    log: ["Three attempts against the Foldseek web API, all 503. Branch abandoned."],
    at: "08:06",
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
    taskNumber: 7,
    duration: "3m 44s",
    outputs: ["alignment.json", "conservation.json"],
    log: [
      "MAFFT L-INS-i over the 412 homologs, Shannon entropy per column.",
      "268 columns informative; the four lowest-entropy positions sit in the groove.",
    ],
    at: "08:12",
  },
  {
    id: "burial",
    col: 3,
    lane: 1.6,
    title: "Confidence & burial",
    capability: "structure",
    status: "COMPLETED",
    thumb: "plddt",
    methods: ["DSSP", "per-residue RSA", "2 models"],
    metric: { label: "buried in both", value: "141 residues" },
    note:
      "Scored across both surviving folds. 141 residues are buried in both; " +
      "9 flip exposure between them, all in the groove loop that run 2 opens.",
    taskNumber: 8,
    duration: "2m 19s",
    outputs: ["residue_annotations.json"],
    log: [
      "DSSP secondary structure and per-residue RSA, scored across both surviving folds.",
      "141 residues buried in both. 9 flip exposure between them — all in the groove loop.",
    ],
    at: "08:48",
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
    taskNumber: 9,
    duration: "5m 51s",
    outputs: ["claims.json"],
    log: ["17 claims extracted with DOIs; 5 concern thermostability directly."],
    at: "08:12",
  },

  {
    id: "ranking",
    col: 4,
    lane: 1,
    title: "Rank candidate sites",
    capability: "design",
    status: "COMPLETED",
    thumb: "contact",
    methods: ["consensus scoring", "cross-model"],
    metric: { label: "shortlist", value: "12 sites" },
    note:
      "9 of 12 sites rank consistently across both folds. The other 3 only " +
      "appear in the run-2 open state — flagged as conformation-dependent " +
      "rather than dropped.",
    taskNumber: 10,
    duration: "1m 48s",
    outputs: ["candidate_sites.json"],
    log: [
      "Consensus scoring over conservation, burial and prior claims, run against both folds.",
      "9 of 12 sites rank consistently. 3 appear only in the run-2 open state.",
    ],
    counterEvidence:
      "The consensus weighting was tuned on the run-1 closed state, so the 3 " +
      "conformation-dependent sites are scored by a rule that assumes the groove is " +
      "shut. Their ranking is not independent of which fold you trust.",
    limitations: ["No experimental activity data enters the score — this is prediction only."],
    structure: {
      file: "/structures/5XJH_A.pdb",
      caption: "The 12 shortlisted sites mapped back onto the fold.",
      triad: [160, 206, 237],
      activity: [159, 238, 241],
      stability: [121, 186, 280, 214],
      focus: null,
      overview: true,
    },
    at: "08:50",
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
    taskNumber: 11,
    duration: "7m 26s",
    outputs: ["control_null.json"],
    log: [
      "Column-shuffled MSA, 200 replicates, same scoring path as the real run.",
      "Null signal 0.04 against 0.61 observed — the conservation signal is not an artefact " +
        "of the scoring pipeline.",
    ],
    at: "08:52",
  },

  {
    id: "md",
    col: 5,
    lane: 0.4,
    title: "MD stability screen",
    capability: "simulation",
    status: "RUNNING",
    thumb: "md",
    methods: ["OpenMM", "2 models × 3 × 100 ns"],
    metric: { label: "progress", value: "62 ns / 100 ns" },
    parallelGroup: "fan-2",
    taskNumber: 12,
    duration: "62m so far",
    outputs: ["traj_partial.dcd"],
    log: [
      "OpenMM, implicit solvent, both surviving folds × 3 replicas × 100 ns.",
      "Backbone RMSD is flattening near 1.8 Å on the run-1 replicas. Nothing parsed yet — " +
        "metrics will be reported only once the runs finish.",
    ],
    at: "08:53",
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
    taskNumber: 13,
    duration: "—",
    log: [
      "Never launched. PET oligomer ligands would have had to be built by hand, and an " +
        "uncurated set would produce scores that look quantitative but are not.",
    ],
    limitations: ["No binding-affinity evidence anywhere in this investigation."],
    at: "08:53",
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
    taskNumber: 14,
    duration: "2m 05s",
    outputs: ["variants.csv"],
    log: ["6 variants designed across the 9 cross-model sites, sized for a single assay plate."],
    at: "08:55",
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
    taskNumber: 15,
    duration: "queued",
    log: ["Waiting on the stability screen before findings can be written."],
    at: "—",
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
  // both surviving folds feed downstream work as competing hypotheses
  { from: "fold-a", to: "burial" },
  { from: "fold-b", to: "burial" },
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
    label: "3 competing runs → 2 kept",
    rule: "kill below pLDDT 70 · keep structurally distinct survivors",
  },
];

/** Header metadata, mirroring the run summary the operator sees elsewhere. */
export const META = {
  protocol: "End-to-end laboratory investigation (default)",
  state: "Working in the sandbox…",
  elapsed: "97m 42s",
  taskCount: 15,
  outputCount: 12,
  updated: "23 Aug, 09:58",
  capabilities: [
    "Literature Search",
    "Sequence Analysis",
    "Structure Analysis",
    "Molecular Simulation",
    "Candidate Ranking",
    "Data Analysis",
    "Research Synthesis",
  ],
};

/** The brief the investigation was launched from. */
export const BRIEF = {
  objective:
    "Raise the catalytic activity of IsPETase (Ideonella sakaiensis PETase) at 50 °C " +
    "without losing the fold. The wild-type enzyme degrades PET efficiently near 30 °C " +
    "but loses structure well below the glass-transition temperature of PET, which is " +
    "where industrial depolymerisation would have to run. Identify substitutions that " +
    "buy thermal margin, and say plainly which of them are predicted to cost activity.",
  questions: [
    "Which positions carry conservation signal that is not an artefact of the scoring pipeline?",
    "Does the substrate groove sample an open state, and does that change which sites matter?",
    "Which candidates survive when scored against more than one predicted conformation?",
  ],
  assumptions: [
    "Public data only — no in-house assay results enter the ranking.",
    "Structure prediction stands in for an experimental structure of the variant.",
    "Ranking is predictive; nothing here has been tested at the bench.",
  ],
  inputs: ["target_ispetase.fasta", "homolog_db.fasta", "protein_engineering_v2 playbook"],
};
