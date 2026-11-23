/**
 * Log viewer for one attempt (story 1-2, AD-1): cursor-paged polling of
 * `GET /runs/{runId}/attempts/{attemptId}/log`, with follow/pause and raw download.
 *
 * **Follow mode** (default): while `isRunning && !eof`, the component polls on every
 * `$poll` tick and auto-scrolls to the bottom whenever new lines arrive.  Scrolling
 * up pauses following; clicking "follow" resumes it.
 *
 * **Download**: the "download raw" link opens `?download=true`, which streams the full
 * file as a `text/plain` attachment; shown only when a file exists.
 *
 * **States**: a page's `state` decides what the panel says. `text` renders the lines; any
 * other state renders exactly one words line (`lib/run/log-state.ts`), so the panel is never
 * empty once its first page has loaded.
 *
 * All log access is via the web-client proxy (AD-1); the browser never touches the log
 * volume directly.
 */
import { useEffect, useRef, useState } from 'react';
import { useStore } from '@nanostores/react';

import { api } from '../../api/client';
import { logWords, showsDownload } from '../../lib/run/log-state';
import { $poll } from '../../stores/poll';
import type { components } from '../../api/schema';

type Meta = Pick<components['schemas']['LogPageOut'], 'state' | 'reason' | 'removed_at'>;

interface Props {
  runId: string;
  attemptId: string;
  isRunning: boolean;
  exitCode: number | null;
  seconds: number | null;
}

export default function LogViewer({ runId, attemptId, isRunning, exitCode, seconds }: Props) {
  const [lines, setLines] = useState<string[]>([]);
  const [cursor, setCursor] = useState(0);
  const [eof, setEof] = useState(false);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [following, setFollowing] = useState(true);
  const containerRef = useRef<HTMLDivElement>(null);
  const pollTick = useStore($poll);

  async function fetchPage(from: number): Promise<void> {
    const { data } = await api.GET('/runs/{run_id}/attempts/{attempt_id}/log', {
      params: { path: { run_id: runId, attempt_id: attemptId }, query: { cursor: from } },
    });
    if (!data) return;
    setMeta({ state: data.state, reason: data.reason, removed_at: data.removed_at });
    if (data.lines.length > 0) {
      setLines((prev) => [...prev, ...data.lines]);
      setCursor(data.next_cursor);
    }
    setEof(data.eof);
  }

  // Initial fetch on mount / when attemptId changes
  useEffect(() => {
    setLines([]);
    setCursor(0);
    setEof(false);
    setMeta(null);
    setFollowing(true);
    void fetchPage(0);
  }, [attemptId]);

  // Poll for new lines while running and not at eof
  useEffect(() => {
    if (!isRunning || eof) return;
    void fetchPage(cursor);
  }, [pollTick, cursor]);

  // Auto-scroll to bottom when new lines arrive in follow mode
  useEffect(() => {
    if (!following || !containerRef.current) return;
    containerRef.current.scrollTop = containerRef.current.scrollHeight;
  }, [lines, following]);

  function handleScroll(): void {
    const el = containerRef.current;
    if (!el) return;
    const atBottom = el.scrollTop >= el.scrollHeight - el.clientHeight - 8;
    if (!atBottom) setFollowing(false);
  }

  const words = meta && logWords({ ...meta, lines }, exitCode, seconds);
  const downloadUrl =
    meta !== null && showsDownload(meta)
      ? `/api/v1/runs/${runId}/attempts/${attemptId}/log?download=true`
      : undefined;

  return (
    <div className="wf-log-viewer">
      <div className="wf-log-toolbar">
        {!following && (
          <button
            type="button"
            className="wf-log-follow"
            onClick={() => {
              setFollowing(true);
              if (containerRef.current) {
                containerRef.current.scrollTop = containerRef.current.scrollHeight;
              }
            }}
          >
            follow
          </button>
        )}
        {downloadUrl && (
          <a href={downloadUrl} className="wf-log-download">
            download raw
          </a>
        )}
      </div>
      <div
        ref={containerRef}
        className="wf-log-lines"
        onScroll={handleScroll}
        data-testid="wf-log-lines"
      >
        {words ? (
          <p className="wf-log-words">{words}</p>
        ) : (
          lines.map((line, i) => (
            // biome-ignore lint/suspicious/noArrayIndexKey: log lines have no stable id
            <div key={i} className="wf-log-line">
              {line}
            </div>
          ))
        )}
        {isRunning && !eof && <div className="wf-log-tail" aria-label="loading" />}
      </div>
    </div>
  );
}
