/**
 * The stop's chat thread on the Run page (story 3-3): `chatThreadText`'s four sentences, the
 * neutral `ChatThreadLine` with the error verbatim, and `Banner` placing it right after the
 * `wf-alert` aside on the alert branch only.
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import Banner from '../../src/components/run/Banner';
import ChatThreadLine from '../../src/components/run/ChatThreadLine';
import { chatThreadText, type ChatThreadOut } from '../../src/lib/run/chat';
import type { RunDetailOut, Token } from '../../src/lib/run/detail';

function detail(chatThread: ChatThreadOut | null, status = 'needs_you'): RunDetailOut {
  return {
    run: {
      id: '1',
      status,
      admitted_signals: [],
      branch: 'epics/1',
      budget_usd: '15',
      compare_urls: [],
      created_at: '2026-11-02T09:00:00Z',
      inputs: {},
      manual_estimate_h: null,
      plan_ref: null,
      project: 'p1',
      repository: 'r1',
      spend_usd: '4.18',
      template: 'epic',
      terminal_session: false,
      version: 1,
      worktree_path: null,
      worktrees: [],
      accepted_paths: [],
    },
    header: {
      meta: {
        project: 'demo',
        repository: 'demo-repo',
        base_branch: 'main',
        folder: 'docs',
        template: 'epic',
        version: 1,
        harness: 'claude',
        started_at: null,
        worktree_path: null,
      },
    },
    alert:
      status === 'needs_you'
        ? { token: 'BLK', reason: 'Which schema?', park_kind: 'blocked', chat_thread: chatThread }
        : null,
    steps: [],
    stories: [],
    cost: {
      spent_usd: '4.18',
      budget_usd: '15.00',
      tokens_in: 0,
      tokens_out: 0,
      wall_clock_seconds: 0,
      active_seconds: 0,
      provisional: false,
      trace_url: null,
    },
    gate_record: [],
    admitted_signals: [],
    summary: null,
  } as RunDetailOut;
}

function banner(value: RunDetailOut, token: Token = 'BLK'): string {
  return renderToStaticMarkup(createElement(Banner, { detail: value, token }));
}

describe('chatThreadText', () => {
  it('states each state as a fact about the post', () => {
    const thread = (state: ChatThreadOut['state']): ChatThreadOut => ({
      provider: 'mattermost',
      state,
      error: null,
    });

    expect(chatThreadText(thread('posting'))).toBe('posting the thread to mattermost');
    expect(chatThreadText(thread('open'))).toBe('thread posted to mattermost');
    expect(chatThreadText(thread('failed'))).toBe('thread post failed; not retried');
    expect(chatThreadText(thread('closed'))).toBe('thread closed');
    expect(chatThreadText({ provider: 'slack', state: 'open', error: null })).toBe(
      'thread posted to slack',
    );
  });
});

describe('ChatThreadLine', () => {
  it('names the state and prints the error verbatim', () => {
    const html = renderToStaticMarkup(
      createElement(ChatThreadLine, {
        thread: { provider: 'slack', state: 'failed', error: '403 <bot> not_in_channel' },
      }),
    );

    expect(html).toContain('data-testid="wf-chat-thread"');
    expect(html).toContain('data-state="failed"');
    expect(html).toContain('thread post failed; not retried');
    expect(html).toContain('data-testid="wf-chat-thread-error"');
    expect(html).toContain('403 &lt;bot&gt; not_in_channel');
  });

  it('shows an error whatever the state, and no error element without one', () => {
    const open = renderToStaticMarkup(
      createElement(ChatThreadLine, {
        thread: { provider: 'mattermost', state: 'open', error: '429 rate limited' },
      }),
    );
    const clean = renderToStaticMarkup(
      createElement(ChatThreadLine, {
        thread: { provider: 'mattermost', state: 'open', error: null },
      }),
    );

    expect(open).toContain('429 rate limited');
    expect(clean).not.toContain('wf-chat-thread-error');
  });
});

describe('Banner · chat thread', () => {
  it('renders the line as the next sibling of the alert aside', () => {
    const html = banner(detail({ provider: 'mattermost', state: 'failed', error: '403 x' }));

    expect(html.startsWith('<aside class="wf-alert" data-testid="wf-alert"')).toBe(true);
    expect(html).toMatch(/<\/aside><p[^>]*data-testid="wf-chat-thread"/);
  });

  it('renders no line when the stop has no thread', () => {
    expect(banner(detail(null))).not.toContain('wf-chat-thread');
  });

  it('renders no line off the alert branch', () => {
    const html = banner(detail(null, 'cancelled'), 'CAN');

    expect(html).not.toContain('wf-chat-thread');
  });
});
