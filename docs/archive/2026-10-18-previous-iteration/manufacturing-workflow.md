# Verification and manufacturing workflow

Close the project before scripted verification or exports. Lock files cause a
refusal, even though the default CLI commands do not save the board. Exact
KiCad 10.0.7 is required. The adapter records argv, stdout/stderr, timestamps,
exit status, and source hashes before and after verification.

```sh
./tools/verify.sh /path/to/project
./scripts/export-manufacturing.sh /path/to/project --revision A
```

Reports go into unique `qa/generated/verify-*` directories. ERC is parsed per
sheet; DRC includes violations, unconnected items and schematic parity. Errors,
warnings and exclusions block the automatic gate. Missing/invalid reports,
nonzero commands or changed source also block it. The kit does not disable any
KiCad checks or refill/save zones; refill them in KiCad before the run. Inspect
the report's `ignored_checks` in the manual ERC/DRC reviews. Empty-board checks
are a format/tooling test, never evidence of electrical readiness.

Draft exports are allowed for inspection even if ERC/DRC fails. They live under
`manufacturing/releases/generated/rev-REV-DRAFT/`, include commands and artifact
SHA-256 values in `manifest.json`, and always say **NO-GO**. Failure of any export
sets `exports_complete: false` and returns exit 21; files remain for diagnosis.
The STEP export needs a valid board outline. Missing vendor 3D models are not
replaced with fake solids. Gerber layer selection uses the CLI's default board
layers; review the actual stackup, fabrication settings and outputs before release.

## Reviewed release

Copy `manufacturing/approval.example.json` to a project-local approval record,
fill every field with real review evidence, and review/sign the existing
`manufacturing/releases/RELEASE_CHECKLIST.md`. Commit reviewed source and evidence
in the independent generated repository. Reference the exact resulting commit
in an external approval JSON (so it does not change the committed source):

```sh
./scripts/export-manufacturing.sh /path/to/project --revision A --approval /path/to/signed-approval.json
```

A GO package requires a clean independent Git repository, an approval naming the
exact commit and revision, approver/date, signed-checklist path, and every gate
PASS or justified NOT_APPLICABLE with a real project-local evidence file. This
includes physical prototype validation where applicable. The tool cannot verify
a human signature or the truth of measurements; reviewers own those attestations.
It verifies file existence, bindings and native tool results. Never use placeholder
approval data to label a real board GO.

Only after fresh ERC/DRC passes, every export succeeds, and source hashes/Git state
remain unchanged is `rev-REV-GO/` published. Evidence, verification reports and
approval are copied into that package. Existing revision directories are never
replaced. Manifests include quality gate, revision, Git state, tool version,
commands, all source hashes and output/evidence hashes. Source hashes include
hierarchical sheets, local libraries and 3D assets. Symlinked design dependencies
are refused because they are not portable.

These outputs are ignored until explicitly archived/reviewed. The tool does not
commit, push, submit fabrication orders, route boards, program devices, sign
approvals or claim physical validation.

Native CLI reference: https://docs.kicad.org/10.0/en/cli/cli.html
