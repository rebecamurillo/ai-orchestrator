/** The PNG background and preview switches shared by the Run and comparison chart views. */
import type { Background } from '../../lib/charts/export';

export type Preview = 'screen' | 'dark' | 'light';

export const BACKGROUNDS: [Background, string][] = [
  ['transparent', 'TRANSPARENT'],
  ['light', 'LIGHT'],
  ['dark', 'DARK'],
];
export const PREVIEWS: [Preview, string][] = [
  ['screen', 'SCREEN'],
  ['dark', 'DARK PAGE'],
  ['light', 'LIGHT PAGE'],
];

export function Switch<T extends string>({
  label,
  options,
  current,
  onPick,
}: {
  label: string;
  options: [T, string][];
  current: T;
  onPick: (next: T) => void;
}) {
  return (
    <div className="wf-metrics-toggle" role="group" aria-label={label}>
      {options.map(([key, text]) => (
        <button
          key={key}
          type="button"
          className="wf-metrics-toggle-btn"
          aria-pressed={key === current}
          onClick={() => onPick(key)}
        >
          {text}
        </button>
      ))}
    </div>
  );
}
