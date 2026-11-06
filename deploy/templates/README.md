# Your workflow files

This folder is mounted read-only into the backend at `/app/operator-templates`
(`OPERATOR_TEMPLATES_DIR`). At start-up the backend loads every `*.yaml` directly under it,
after the shipped set, and your file wins: a changed file is stored as the next version of its
name.

- The file name is the template name: `bench.yaml` must say `name: bench`.
- A file that cannot be read, does not validate or would break a stored caller is refused and
  logged; the instance keeps running and nothing already stored is deleted or changed.
- Files starting with `.`, and names not ending in `.yaml`, are ignored; a file over 1 MiB is
  refused.
- A name that matches a shipped template overrides it; the shipped file is untouched.

The file format, with examples, is in `templates/README.md` of the repository. The `*.yaml`
files you put here are yours and are not tracked by git.
