# Catalyst

Catalyst combines a CPU-native bioinformatics pipeline with a local dashboard for demonstrating a Devin-style computational bioengineering workflow.

This repository contains CPU-native scientific vertical slices. A target
protein FASTA is searched against a FASTA database with MMseqs2, aligned with
MAFFT, and analyzed for per-column conservation in pure Python/NumPy. The
structure slice maps a deposited PDB chain to the target and MSA, computes
DSSP annotations, and searches a committed reference set with Foldseek.

## Local orchestration dashboard

The dashboard can:

- submit a protein-engineering objective,
- watch Sequence and Structure workers run in parallel,
- inspect normalized activity and downloadable scientific artifacts,
- review an evidence-labeled mutation shortlist,
- apply a follow-up constraint without rerunning unaffected tools.

The local executor runs real MAFFT, DSSP, and Bio.PDB calculations against a curated IsPETase dataset. Its ranking is a transparent demonstration and **not an experimental claim of 60 °C performance**.

### Start locally

The repository snapshot already contains Python 3.12, the `.venv`, and the CPU bioinformatics tools.

```bash
.venv/bin/pip install -e '.[dev]'
npm --prefix frontend install
./scripts/start-local.sh
```

Open http://localhost:3000. The FastAPI API and interactive docs run at http://localhost:8000 and http://localhost:8000/docs.

To use a different API origin:

```bash
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 npm --prefix frontend run dev
```

### Demonstration flow

1. Launch the prefilled PETase objective.
2. Watch the coordinator start Sequence and Structure workers.
3. Observe a real missing-structure-input failure and successful DSSP retry.
4. Download the alignment, conservation, structure, DSSP, and distance artifacts.
5. Review the candidate table and evidence categories.
6. Submit `Exclude mutations within 10 Å of the catalytic site.`
7. See a new result version without rerunning MAFFT or DSSP.

Local state is written under `backend/.local/` and is excluded from Git.

### Enable managed Devin credits

Local mode remains the default and consumes no ACUs. Managed mode launches two specialist sessions and one coordinator session through the v3 Devin API.

1. Open [Service users](https://app.devin.ai/settings/devin-api?tab=service-users#org-service-users-list), create a dedicated account, and assign a role with `UseDevinSessions`, `ViewOrgSessions`, and `ManageOrgSessions`.
2. Generate its one-time `cog_` API key. A supported personal access token from the API Keys tab can be used instead.
3. Copy `.env.devin.example` to `.env.devin`, enter the server-side key and organization ID, and choose the per-session ACU cap.
4. Start the app and select **Managed Devin · uses credits** before launching a run.

The browser receives only execution mode, session links, statuses, and ACU totals. It never receives the API key. One managed run creates three sessions, so a 2-ACU per-session cap permits a theoretical maximum of 6 ACUs. The app never launches managed sessions unless that mode is explicitly selected.

## CPU-native pipeline

The `bioctl` pipeline searches a FASTA database with MMseqs2, aligns hits with MAFFT, and analyzes per-column conservation in Python/NumPy.

It writes validated `homolog_search.json`, `alignment.json`, `conservation.json`, and `run.json` artifacts next to the intermediate FASTA files. Each artifact has a committed JSON Schema under `schemas/` and includes tool/file provenance. MMseqs2 percent identity is reported on a 0-100 scale, and every run records tool parameters and artifact digests.

Evidence is labeled `KNOWN` for pinned UniProt fixture/database sequences and `CALCULATED` for direct MMseqs2/MAFFT/conservation output. `PREDICTED` and `EXPERIMENTAL` are reserved for future evidence; nothing in this repository is experimentally validated.

Run its smoke test with:

```bash
./scripts/smoke_test.sh
```

It runs the committed fixtures into the ignored `runs/` directory and prints
the hit count, alignment length, and top conserved target positions.

The structure smoke test is:

```sh
./scripts/structure_smoke_test.sh
```

It first runs the sequence pipeline, then writes structure artifacts into
`runs/structure_smoke` and prints modelled residues, unmodelled target ranges,
secondary-structure composition, the top Foldseek hit, and the catalytic-triad
mapping. Structure coordinates use three distinct systems: `structure_index`
is the extracted chain sequence index used by Foldseek, `author_residue` is
PDB author numbering plus insertion code, and `target_position` is the
1-based target FASTA position. MSA columns are mapped through target
positions rather than assumed author numbering.

Deposited coordinates and metadata are `KNOWN`; DSSP, Foldseek, and all
sequence-to-structure mappings are `CALCULATED`. None of these results are
experimental validation. Structure annotations also record warnings for
unmodelled residues, numbering irregularities, alternate locations, and
residues excluded or absent from DSSP.
RSA is the raw Sander quotient and can exceed 1 for highly exposed residues,
so such values are flagged rather than clipped.

## Candidate-site ranking

The candidate stage consumes the structure annotations and sequence alignment
artifacts and writes `candidate_sites.json`. It produces two separate,
transparent heuristic shortlists:

- `activity` ranks substrate-cleft sites with
  `d <= 12.0`, `conservation < 0.98`, and `rsa < 0.50`.
  Its score is
  `0.50 * proximity + 0.30 * plasticity + 0.20 * burial`.
- `stability` ranks surface sites away from the active site with
  `d >= 12.0`, `conservation < 0.90`, and `rsa >= 0.25`.
  Its score is
  `0.35 * exposure + 0.30 * variability + 0.20 * remoteness + 0.15 * loop`.

The shared feature definitions are `lin(x, lo, hi) = clamp((x - lo) /
(hi - lo), 0, 1)`, `proximity = 1 - lin(d, 4.0, 12.0)`,
`remoteness = lin(d, 12.0, 25.0)`, `burial = 1 - lin(rsa, 0.0, 0.5)`,
`exposure = lin(rsa, 0.0, 0.5)`,
`plasticity = 1 - lin(conservation, 0.60, 0.98)`,
`variability = 1 - lin(conservation, 0.50, 0.90)`, and `loop = 1.0` for
coil (`C`) and `0.0` otherwise. Fully conserved sites are excluded because
the activity and stability filters require sequence variability, and the
catalytic triad is excluded by default to protect the catalytic residues.

Substitution options are observed residues in the homolog alignment only:
non-gap alternatives occurring at least twice and at frequency at least
`0.15`. They are not predictions, recommendations, or beneficial-effect
claims. The candidate rankings are not predictions of activity or stability,
carry no effect estimate, and are not experimental validation.

The candidate smoke test is:

```sh
./scripts/candidate_smoke_test.sh
```

## V1 orchestration contract

The versioned [protein-engineering V1 playbook](playbooks/protein_engineering_v1.md)
defines the operator-facing procedure over the sequence, structure, and
candidate slices. Run the complete investigation with:

```sh
bioctl investigate \
  --objective "Identify substrate-cleft and surface engineering sites" \
  --target fixtures/target_ispetase.fasta \
  --database fixtures/homolog_db.fasta \
  --structure fixtures/structures/6EQE.pdb.gz \
  --chain A \
  --references fixtures/structures \
  --out runs/investigate
```

The command writes stage outputs under `sequence/`, `structure/`, and
`candidates/`, plus the schema-validated `final_result.json`. The report
records stage statuses and continues to write the report when a stage fails:
later stages become `SKIPPED` and the command exits 1. Constraints are labeled
`ENFORCED_BY_PIPELINE` only when passed through to candidate ranking; other
constraints are `RECORDED_ONLY`.

The playbook is versioned as `protein-engineering-v1` version `1.0.0`, and its
path and digest are pinned in the final report. The fourth smoke test is:

```sh
./scripts/investigate_smoke_test.sh
```

## Development

```bash
# Python
.venv/bin/ruff check backend
.venv/bin/ruff format --check backend
.venv/bin/pytest

# Frontend
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

## Devin integration boundary

The dashboard currently defaults to a deterministic local executor so it runs without external credentials. The run, agent, event, artifact, candidate, and follow-up contracts match the proposed managed-Devin control plane; connecting real managed sessions requires a supported `cog_` service-user key because legacy `apk_` keys cannot access v3 or Devin MCP.

