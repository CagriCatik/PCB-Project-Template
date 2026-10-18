# Validation scope

Source-kit regression tests are separate from engineering validation of a real
board. The mandatory layout and baseline are checked only in the source kit;
generated board documentation is intended to be edited. `test_template.py`
continues to check generated project's domain contracts. KiCad GUI intentionally
omits `meta/`, so that one metadata test is skipped for GUI-generated projects.

Run native integration tests with `KICAD_NATIVE_TESTS=1`. The positive fixture is
a board with only a rectangular outline: passing ERC/DRC proves tooling behavior,
not a working circuit. The tests also require a blank-outline failure and invalid
schematic failure and verify NO-GO export labeling. Test-created artifacts are
in `qa/generated/native-integration/`, and are excluded from source archives.

The implementation report records actual execution results, limitations, and
files changed. No production firmware target, live routing, vendor model,
electrical measurement or physical prototype result is implied by these tests.
