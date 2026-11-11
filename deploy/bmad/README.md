# BMAD script

`install.sh` brings each harness to the BMAD version of this release.

- It deletes what its last run recorded in `.orchestrator/bmad.json`. With no record it
  deletes every `bmad-*` entry of the harnesses' asset folders. Names starting `bmad-` are
  reserved to BMAD.
- It installs the BMAD package in the image (`/opt/bmad`, `BMAD_VERSION`) into each
  harness's skills folder, offline, then writes the record.
- A failed run changes nothing: the installs happen in a scratch directory first, and the
  record is written last.
- The setup runner runs it when `setup/bmad.choice` reads `installed` (a missing file reads
  `installed`), at install, at upgrade and on demand.

## Remove, install, restore

- `./install.sh bmad remove` deletes the recorded entries and writes `removed`.
- `./install.sh bmad install` writes `installed` and runs the setup runner.
- To restore the product's script after a local edit, extract `bmad/install.sh` again with
  `kit bootstrap` of the running tag.

A repository's `_bmad/` (`repo-init`, `bmad.install`) does not depend on this choice.
