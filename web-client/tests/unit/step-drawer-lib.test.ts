import { describe, expect, it } from 'vitest';

import {
  drawerRequestPath,
  filesReadLines,
  filesWrittenLines,
  headerLines,
  isAgentStep,
  logHeading,
  runOrderView,
} from '../../src/lib/run/step-drawer';
import { agentDrawer, shellDrawer } from '../fixtures/step-drawer';

describe('step drawer lib', () => {
  it('builds the request path and the log heading', () => {
    expect(drawerRequestPath('r1', 13, 2)).toBe('/runs/r1/steps/13/attempts/2/drawer');
    expect(logHeading(2)).toBe('LOG · ATTEMPT 2');
  });

  it('reads an agent header with attempts and cost', () => {
    const out = agentDrawer();
    expect(isAgentStep(out.header)).toBe(true);
    expect(headerLines(out)).toEqual({
      label: 'build',
      path: 'epics[0].stories[0].build',
      token: 'RUN',
      kindGate: 'agent · liveness',
      figure: '2 attempts · $1.25',
    });
    expect(headerLines(agentDrawer({ header: { cost_usd: null } })).figure).toBe('2 attempts · $0');
  });

  it('reads a non-agent header with duration and exit code', () => {
    const lines = headerLines(shellDrawer());
    expect(isAgentStep(shellDrawer().header)).toBe(false);
    expect(lines.kindGate).toBe('shell · deterministic');
    expect(lines.figure).toBe('2m · exit 0');
    expect(
      headerLines(shellDrawer({ header: { started_at: null, ended_at: null, exit_code: null } }))
        .figure,
    ).toBe('— · exit —');
    expect(headerLines(shellDrawer({ header: { ended_at: null } })).figure).toBe('— · exit 0');
  });

  it('builds the run order with the current row marked, or none', () => {
    const view = runOrderView(agentDrawer())!;
    expect(view.heading).toBe('RUN ORDER · epics[0].stories[0]');
    expect(view.rows.map((r) => [r.seq, r.phase, r.label, r.kind, r.token, r.current])).toEqual([
      [12, 'BEFORE', 'sync', 'shell', 'DON', false],
      [13, 'AGENT', 'build', 'agent', 'RUN', true],
      [14, 'AFTER', 'verify', 'shell', 'QUE', false],
    ]);
    expect(runOrderView(agentDrawer({ run_order: null }))).toBeNull();
  });

  it('reads every files-read state', () => {
    expect(filesReadLines({ state: 'listed', paths: ['a', 'b'] })).toEqual(['a', 'b']);
    expect(filesReadLines({ state: 'none', paths: [] })).toEqual(['this step read no file']);
    expect(filesReadLines({ state: 'not_recorded', paths: [] })).toEqual([
      'deterministic step · files read are not recorded; the command is in the log',
    ]);
  });

  it('reads every files-written state', () => {
    const base = { commit: null, refs: [], files: [] };
    expect(
      filesWrittenLines({
        ...base,
        state: 'files',
        files: [
          { path: 'a', added: 3, removed: 1 },
          { path: 'img', added: null, removed: null },
        ],
      }),
    ).toEqual(['a +3 −1', 'img binary']);
    expect(
      filesWrittenLines({
        ...base,
        state: 'commit',
        commit: { sha: 'abcdef123456', message: 'story 1' },
        files: [{ path: 'a', added: 1, removed: 0 }],
      }),
    ).toEqual(['commit abcdef1 · story 1', 'a +1 −0']);
    expect(
      filesWrittenLines({ ...base, state: 'commit', commit: { sha: 'abcdef123', message: null } }),
    ).toEqual(['commit abcdef1']);
    expect(filesWrittenLines({ ...base, state: 'commit', commit: null })).toEqual([]);
    expect(filesWrittenLines({ ...base, state: 'refs', refs: ['main a → b', 'x c → d'] })).toEqual([
      'no file · refs updated: main a → b',
      'no file · refs updated: x c → d',
    ]);
    expect(filesWrittenLines({ ...base, state: 'none' })).toEqual(['no file']);
  });
});
