# Kit test suite

Automated tests for the PCB-Project-Template tooling. Run everything with
`python3 test_template.py` (or `python3 -m unittest discover -s qa/tests -v`).

- Native KiCad integration tests run automatically when KiCad 10.0.7 is
  installed; set `KICAD_NATIVE_TESTS=0` to skip them.
- Tests never touch real user state: `kit_test_support.py` redirects the kit
  state and KiCad user-template directories into a temporary sandbox whose path
  contains spaces.
- Board-level verification test cases for generated projects live in
  `qa/project-template/tests/README.md` (copied to each project's `qa/tests/`).
