// Mock contents for the files each task writes, so output chips in the dock
// open something real. JSON bodies follow the shapes in /schemas.

export type Artifact = {
  kind: "json" | "text" | "binary";
  bytes: string;
  /** Rendered preview. Absent for binary formats. */
  body?: string;
  /** Shown instead of a body for formats there is no point printing. */
  summary?: string;
};

const PROVENANCE = {
  tool_versions: { jackhmmer: "3.4", mafft: "7.525", dssp: "4.4.0" },
  generated_at: "2026-08-23T08:12:04Z",
  playbook: "protein_engineering_v2",
};

const json = (value: unknown) => JSON.stringify(value, null, 2);

export const ARTIFACTS: Record<string, Artifact> = {
  "homolog_search.json": {
    kind: "json",
    bytes: "184 KB",
    body: json({
      schema_version: "1.0.0",
      target_id: "ispetase_wt",
      database_path: "fixtures/homolog_db.fasta",
      counts: { searched: 41822, hits: 412, retained: 412 },
      diversity: { mean_percent_identity: 38.4, effective_sequences: 191 },
      hits: [
        { accession: "A0A0K8P6T7", description: "PETase [Ideonella sakaiensis]", percent_identity: 100.0, evalue: 0.0 },
        { accession: "Q9RA96", description: "Cutinase-like [Thermobifida fusca]", percent_identity: 52.1, evalue: 3.1e-71 },
        { accession: "P00590", description: "Cutinase [Fusarium solani]", percent_identity: 27.8, evalue: 4.4e-19 },
        { accession: "…409 more", description: "", percent_identity: 0, evalue: 0 },
      ],
      provenance: PROVENANCE,
    }),
  },

  "conservation.json": {
    kind: "json",
    bytes: "96 KB",
    body: json({
      schema_version: "1.0.0",
      target_id: "ispetase_wt",
      summary: { informative_columns: 268, mean_conservation: 0.41 },
      top_conserved_positions: [160, 206, 237, 208],
      columns: [
        { target_position: 159, target_residue: "W", conservation: 0.71, entropy: 1.04, informative: true },
        { target_position: 160, target_residue: "S", conservation: 0.98, entropy: 0.08, informative: true },
        { target_position: 206, target_residue: "D", conservation: 0.96, entropy: 0.14, informative: true },
        { target_position: 237, target_residue: "H", conservation: 0.97, entropy: 0.11, informative: true },
        { target_position: 238, target_residue: "S", conservation: 0.44, entropy: 1.92, informative: true },
      ],
      provenance: PROVENANCE,
    }),
  },

  "residue_annotations.json": {
    kind: "json",
    bytes: "72 KB",
    body: json({
      schema_version: "1.0.0",
      target_id: "ispetase_wt",
      models_scored: ["fold_run1.pdb", "fold_run2.pdb"],
      disagreement: { count: 9, positions: [86, 87, 88, 159, 160, 238, 239, 240, 241] },
      annotations: [
        { author_residue: 159, target_position: 159, one_letter: "W", conservation: 0.71, rsa: 0.34, secondary_structure: "C" },
        { author_residue: 160, target_position: 160, one_letter: "S", conservation: 0.98, rsa: 0.08, secondary_structure: "H" },
        { author_residue: 238, target_position: 238, one_letter: "S", conservation: 0.44, rsa: 0.51, secondary_structure: "C" },
      ],
      provenance: PROVENANCE,
    }),
  },

  "candidate_sites.json": {
    kind: "json",
    bytes: "31 KB",
    body: json({
      schema_version: "1.0.0",
      target_id: "ispetase_wt",
      evidence_type: "PREDICTED",
      parameters: { scored_against: ["fold_run1.pdb", "fold_run2.pdb"], weighting_tuned_on: "fold_run1.pdb" },
      score_definitions: { score: "weighted consensus of conservation, burial and prior claims" },
      feature_definitions: { conservation: "1 - normalised Shannon entropy" },
      shortlists: {
        activity: {
          sites: [
            { rank: 1, author_residue: 159, one_letter: "W", target_position: 159, score: 0.88, conservation: 0.71 },
            { rank: 2, author_residue: 238, one_letter: "S", target_position: 238, score: 0.81, conservation: 0.44 },
            { rank: 3, author_residue: 241, one_letter: "N", target_position: 241, score: 0.63, conservation: 0.39 },
          ],
        },
        stability: {
          sites: [
            { rank: 1, author_residue: 121, one_letter: "S", target_position: 121, score: 0.79, conservation: 0.52 },
            { rank: 2, author_residue: 186, one_letter: "D", target_position: 186, score: 0.74, conservation: 0.58 },
            { rank: 3, author_residue: 280, one_letter: "R", target_position: 280, score: 0.68, conservation: 0.47 },
          ],
        },
      },
      warnings: ["3 sites rank only in the fold_run2 open conformation: 86, 87, 240"],
      limitations: ["No experimental activity data enters the score — this is prediction only."],
      provenance: PROVENANCE,
    }),
  },

  "claims.json": {
    kind: "json",
    bytes: "22 KB",
    body: json({
      schema_version: "1.0.0",
      target_id: "ispetase_wt",
      counts: { extracted: 17, with_doi: 17, thermostability: 5 },
      claims: [
        {
          id: "c-01",
          statement: "S238F/W159H raises PET-degrading activity relative to wild type.",
          doi: "10.1073/pnas.1718804115",
          supports: [159, 238],
          strength: "DEMONSTRATED",
        },
        {
          id: "c-02",
          statement: "S121E/D186H/R280A confers a higher melting temperature.",
          doi: "10.1038/s41929-021-00616-y",
          supports: [121, 186, 280],
          strength: "DEMONSTRATED",
        },
        {
          id: "c-03",
          statement: "The substrate-binding groove is unusually flexible in IsPETase.",
          doi: "10.1038/s41467-018-02881-1",
          supports: [159, 238, 241],
          strength: "INFERRED",
        },
      ],
      provenance: PROVENANCE,
    }),
  },

  "control_null.json": {
    kind: "json",
    bytes: "9 KB",
    body: json({
      schema_version: "1.0.0",
      target_id: "ispetase_wt",
      control: "column-shuffled MSA",
      replicates: 200,
      observed_signal: 0.61,
      null_signal: { mean: 0.04, sd: 0.02, p95: 0.08 },
      verdict: "PASS",
      interpretation: "Observed conservation signal is far outside the null; not a pipeline artefact.",
      provenance: PROVENANCE,
    }),
  },

  "literature.json": {
    kind: "json",
    bytes: "58 KB",
    body: json({
      schema_version: "1.0.0",
      query: "IsPETase OR \"PET hydrolase\" AND (thermostability OR activity)",
      counts: { screened: 38, read_full: 12, cited: 9 },
      sources: ["PubMed", "EuropePMC"],
      date_range: "2019-01-01..2026-08-23",
      provenance: PROVENANCE,
    }),
  },

  "alignment.json": { kind: "json", bytes: "412 KB", summary: "MAFFT L-INS-i alignment, 412 sequences × 290 columns. Too large to preview here." },
  "plddt_run1.json": {
    kind: "json",
    bytes: "14 KB",
    body: json({
      schema_version: "1.0.0",
      model: "fold_run1.pdb",
      mean_plddt: 91.4,
      region_means: { catalytic_triad: 94.8, substrate_groove: 88.1, termini: 71.2 },
      below_70_residues: [30, 31, 291, 292],
    }),
  },

  "variants.csv": {
    kind: "text",
    bytes: "412 B",
    body: [
      "variant,positions,rationale,plate_well",
      "W159H,159,activity hotspot (c-01),A1",
      "S238F,238,activity hotspot (c-01),A2",
      "W159H/S238F,159;238,double from c-01,A3",
      "S121E,121,stability set (c-02),B1",
      "D186H,186,stability set (c-02),B2",
      "R280A,280,stability set (c-02),B3",
    ].join("\n"),
  },

  "fold_run1.pdb": { kind: "text", bytes: "156 KB", summary: "PDB coordinates, 1951 ATOM records, chain A. Rendered in the structure view above." },
  "fold_run2.pdb": { kind: "text", bytes: "156 KB", summary: "PDB coordinates for the alternate open-groove model." },
  "traj_partial.dcd": { kind: "binary", bytes: "1.4 GB", summary: "Binary MD trajectory, still being written. 62 ns of 100 ns." },
};
