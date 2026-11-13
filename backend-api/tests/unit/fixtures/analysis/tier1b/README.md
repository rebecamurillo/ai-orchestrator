# Tier 1b fixtures

Every file here is one of three kinds. Nothing is a binary or a `node_modules` folder.

## Recorded: the output of the real tool, written verbatim

| File | Tool, version | Command |
| --- | --- | --- |
| `jscpd-report.json` | jscpd 5.4.3 (npm) | `jscpd --reporters sarif,json --output <dir> files/a.py files/b.py files/c.py files/d.py`, run in `jscpd-input/` |
| `jscpd-sarif.json` | jscpd 5.4.3 | the `jscpd-report.sarif` the same run wrote (named `.json` here; it holds the recorder's absolute scan folder in `originalUriBaseIds`, which the code makes relative before storing, see `test_tier1b.py`) |
| `jscpd-version.txt` | jscpd 5.4.3 | `jscpd --version` |
| `jscpd-folders-output/jscpd-report.sarif`, `jscpd-folders-output/jscpd-report.json` | jscpd 5.4.3 (npx) | `npx --yes jscpd@5.4.3 --reporters sarif,json --output <absolute path of jscpd-folders-output> <absolute paths of jscpd-folders-input/files/src/billing/invoice.py, lib/report/summary.py, api/helpers.py, web/helpers.py>`; both files are written by jscpd itself, unedited. The SARIF holds one `originalUriBaseIds` entry per folder (the recorder's absolute paths, which `test_tier1b.py` moves to its scan root); the JSON names every fragment by its bare basename, which is why the code reads paths from the SARIF only (Operator ruling 2026-11-13) |
| `lizard.csv` | lizard 1.26.0 | `uv tool run --from lizard==1.26.0 lizard --csv <absolute paths of lizard-input/files/a.py and b.ts>` |
| `lizard-cognitive.csv` | lizard 1.26.0 | the same with `-Ecognitive` |
| `lizard-version.txt` | lizard 1.26.0 | `uv tool run --from lizard==1.26.0 lizard --version` |

lizard's CSV has no header. Columns: `nloc, ccn, tokens, params, length, "name@start-end@file",
file, name, longname, start, end`, then, with `-Ecognitive`, `cognitive` as a twelfth column.
The `file` column holds the folder the output was recorded in; `test_tier1b.py` points it at
the scratch folder the code scans.

jscpd 5.x writes SARIF itself; the `@jscpd/sarif-reporter` package the story named does not
exist on npm (checked 2026-11-13), so only `jscpd` is installed.

## Input files written by hand (the programs the tools were run on, and lock-file samples)

`jscpd-input/files/*.py` (a and b share one clone, c and d another),
`jscpd-folders-input/files/{src/billing/invoice.py, lib/report/summary.py}` (one clone across two
folders) and `{api,web}/helpers.py` (one clone between two files with the same basename), `lizard-input/files/a.py`
(`changed_fn` at cyclomatic 22 and cognitive 21, `unchanged_fn` at 30 and 29) and `b.ts`,
`pnpm-lock.{base,head}.yaml`, `package-lock.{base,head}.json`, `uv.{base,head}.lock`,
`poetry.{base,head}.lock`, `package.{base,head}.json`: samples in each tool's documented
format for the dependency diff.

## Synthetic: shaped on documented output, never recorded

No live registry or advisory query was made for these; each test that reads one says so.

| File | Imitates |
| --- | --- |
| `synthetic-osv.sarif` | osv-scanner 2.7.1 `--format sarif` (SARIF 2.1.0, one result per vulnerable package) |
| `synthetic-osv.json` | osv-scanner 2.7.1 `--format json` (`results[].packages[].package{name, version}`) |
| `synthetic-npm-left-pad.json` | the npm registry's package document (`time.created`, `versions[v].license`, `license`) |
| `synthetic-pypi-requests.json` | PyPI's `/pypi/{name}/json` (`info.license`, `info.license_expression`, `releases[v][].upload_time_iso_8601`) |

osv-scanner has no version fixture: its binary was not run. The pinned 2.7.1 comes from the
release's `osv-scanner_SHA256SUMS`, and `synthetic-osv.sarif` carries it as the version it
imitates.
