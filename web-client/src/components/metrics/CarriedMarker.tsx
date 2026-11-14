import '../../styles/metrics.css';

export default function CarriedMarker({ from }: { from: number }) {
  return <span className="metric-carried">from v{from}</span>;
}
