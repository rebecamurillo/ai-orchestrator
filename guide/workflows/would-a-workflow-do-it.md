---
title: Would a workflow do it?
kind: procedure
audience: any
---
# Would a workflow do it?

Before asking for a new feature, draft a workflow for the need. A workflow is a template
that composes the step kinds the orchestrator already has.

1. Write the workflow as a template YAML file for the need.
2. Check it with `POST /api/v1/templates/{name}/validate`. The answer lists findings.
3. For each finding, read its guide page: the `guide` field of the finding holds the page id,
   `errors/{code}`. The page states what the check rejects and how to fix it.
4. Fix the template and validate again until the findings list is empty.
5. If the validated workflow does the job, use it. No feature is needed.
6. Only when no workflow can do it, go to `feature-request`.
