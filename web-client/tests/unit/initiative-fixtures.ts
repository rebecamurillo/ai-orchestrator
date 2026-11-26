/** Shared InitiativeDetailOut fixture for the story 11.1 component tests. */
import type { components } from '../../src/api/schema';

export type Detail = components['schemas']['InitiativeDetailOut'];
export type Workflow = components['schemas']['DetailWorkflowOut'];
export type Step = components['schemas']['DetailStepOut'];

export const step = (id: string, over: Partial<Step> = {}): Step =>
  ({
    id,
    kind: 'conversation',
    status: 'planned',
    token: 'QUE',
    line: '',
    agent: null,
    turns: [],
    ...over,
  }) as unknown as Step;

export const workflow = (name: string, position: number, over: Partial<Workflow> = {}): Workflow =>
  ({
    workflow: name,
    position,
    type: 'interactive',
    template: `${name}-flow`,
    version: 3,
    run_id: null,
    token: null,
    line: '',
    steps: [],
    files: [],
    status: null,
    ...over,
  }) as unknown as Workflow;

export const STEP_IDS = ['product', 'arch', 'ux', 'plan', 'review', 'close'];

export function detail(over: Partial<Detail> = {}): Detail {
  const steps = STEP_IDS.map((id, i) =>
    step(id, {
      status: i < 2 ? 'done' : i === 2 ? 'running' : 'planned',
      token: i < 2 ? 'DON' : i === 2 ? 'RUN' : 'QUE',
      line: i === 2 ? 'your turn · 14 turns' : '',
      agent: 'analyst',
    }),
  );
  return {
    id: 'ini-1',
    slug: 'familio-dessin-v2',
    name: 'Familio Dessin v2',
    status: 'running',
    workflow: 'spec',
    step: 'ux',
    current_step: 'ux',
    current_position: 1,
    workflow_count: 2,
    attention: 'your_turn',
    reason: '',
    hub: { id: 'h1', slug: 'hub-repo' },
    folder: 'initiatives/familio-dessin-v2',
    package: 'orchestrator-default',
    sequence_fixed_at: '2026-11-20T10:00:00Z',
    created_at: '2026-11-19T09:00:00Z',
    project: { id: 'p1', name: 'Familio' },
    project_id: 'p1',
    project_name: 'Familio',
    repo_tag: ['familio-web', 'familio-api'],
    runs: [],
    workflows: [
      workflow('spec', 1, { token: 'RUN', line: 'ux · your turn', steps }),
      workflow('build', 2, { type: 'auto', token: null, line: 'waits for spec' }),
    ],
    ...over,
  } as unknown as Detail;
}
