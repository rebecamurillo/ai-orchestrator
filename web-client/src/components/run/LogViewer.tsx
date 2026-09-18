/**
 * Log viewer for one attempt (story 1-2, AD-1): cursor-paged polling of
 * `GET /runs/{runId}/attempts/{attemptId}/log`, with follow/pause and raw download.
 *
 * **Follow mode** (default): while `isRunning && !eof`, the component polls on every
 * `$poll` tick and auto-scrolls to the bottom whenever new lines arrive.  Scrolling
 * up pauses following; clicking "follow" resumes it.
 *
 * **Download**: the "download raw" link opens `?download=true`, which streams the full
 * file as a `text/plain` attachment.
 *
 * **GC'd log**: the backend returns `"log no longer on disk"` as a plain text line (not
 * an error) — the viewer renders it like any other line.
 *
 * All log access is via the web-client proxy (AD-1); the browser never touches the log
 * volume directly.
 */
import { useEffect, useRef, useState } from 'react';
import { useStore } from '@nanostores/react';

import { api } from '../../api/client';
import { $poll } from '../../stores/poll';

interface Props {
  runId: string;
  attemptId: string;
  isRunning: boolean;
  /** The attempt's `log_path` — used only to determine whether the download link is
   * meaningful.  The viewer always polls the paged endpoint regardless. */
  logPath: string | null;
}

export default function LogViewer({ runId, attemptId, isRunning, logPath }: Props) {
  const [lines, setLines] = useState<string[]>([]);
  const [cursor, setCursor] = useState(0);
  const [eof, setEof] = useState(false);
  const [following, setFollowing] = useState(true);
  const containerRef = useRef<HTMLDivElement>(null);
  const pollTick = useStore($poll);

  async function fetchPage(from: number): Promise<void> {
    const { data } = await api.GET('/runs/{run_id}/attempts/{attempt_id}/log', {
      params: { path: { run_id: runId, attempt_id: attemptId }, query: { cursor: from } },
    });
    if (!data) return;
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

  const downloadUrl = logPath
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
        {lines.length === 0 && !isRunning && eof && (
          <span className="wf-log-empty">no log output</span>
        )}
        {lines.map((line, i) => (
          // biome-ignore lint/suspicious/noArrayIndexKey: log lines have no stable id
          <div key={i} className="wf-log-line">
            {line}
          </div>
        ))}
        {isRunning && !eof && <div className="wf-log-tail" aria-label="loading" />}
      </div>
    </div>
  );
}
