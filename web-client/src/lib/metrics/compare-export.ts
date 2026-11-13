/** The one-click export: both reads carry the comparison's own query; nothing is saved unless both answer. */
import { api } from '../../api/client';
import { browserEnv, today } from '../charts/export';
import {
  compareQuery,
  exportFailedLine,
  exportLine,
  fileNameOf,
  type CompareState,
} from './compare';

export type ExportResult = { ok: true; line: string } | { ok: false; line: string };

interface Read {
  blob: Blob;
  disposition: string | null;
}

async function read(
  path: '/metrics/compare.csv' | '/metrics/compare.json',
  state: CompareState,
): Promise<Read | string> {
  const shown = `/api${path}`;
  try {
    const { data, response } = await api.GET(path, {
      params: { query: compareQuery(state) },
      parseAs: 'blob',
    });
    if (response.status < 200 || response.status > 299 || !data) {
      return exportFailedLine(shown, response.status);
    }
    return {
      blob: data as unknown as Blob,
      disposition: response.headers.get('Content-Disposition'),
    };
  } catch {
    return exportFailedLine(shown, 'network');
  }
}

export async function exportComparison(
  state: CompareState,
  project: string,
  save: (blob: Blob, fileName: string) => void = browserEnv.save,
): Promise<ExportResult> {
  const csv = await read('/metrics/compare.csv', state);
  const json = await read('/metrics/compare.json', state);
  if (typeof csv === 'string') return { ok: false, line: csv };
  if (typeof json === 'string') return { ok: false, line: json };
  const stem = `${project}-compare-${today()}`;
  const csvName = fileNameOf(csv.disposition, `${stem}.csv`);
  const jsonName = fileNameOf(json.disposition, `${stem}.json`);
  const parsed = JSON.parse(await json.blob.text()) as { runs: unknown[]; catalogue: unknown[] };
  save(csv.blob, csvName);
  save(json.blob, jsonName);
  return {
    ok: true,
    line: exportLine(
      csvName.replace(/\.csv$/, ''),
      parsed.runs.length,
      parsed.catalogue.length,
      state.blind,
    ),
  };
}
