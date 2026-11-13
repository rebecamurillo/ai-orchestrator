import '../../styles/metrics.css';

/** The API's `missing` word, printed as given. */
export default function MissingWord({ word }: { word: string }) {
  return <span className="metric-missing">{word}</span>;
}
