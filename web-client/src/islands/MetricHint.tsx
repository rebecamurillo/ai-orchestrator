/** A catalogue hint control for a figure rendered by an Astro page. */
import { useEffect } from 'react';

import HintControl from '../components/metrics/HintControl';
import { loadCatalogue } from '../stores/catalogue';

export default function MetricHint({ metricId }: { metricId: string }) {
  useEffect(() => void loadCatalogue(), []);
  return <HintControl metricId={metricId} />;
}
