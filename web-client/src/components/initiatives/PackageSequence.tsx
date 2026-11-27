/** The right column of the New initiative page: the package and the workflows it will run. */
import {
  folderLine,
  packageLine,
  sequenceBands,
  type PackageOut,
  type ProjectRead,
} from '../../lib/initiatives/new';

interface Props {
  pkg: PackageOut;
  project: ProjectRead | null;
}

export default function PackageSequence({ pkg, project }: Props) {
  const bands = sequenceBands(pkg, project);
  return (
    <div className="newini-package">
      <h2 className="newini-head">PACKAGE</h2>
      <p>{packageLine(pkg)}</p>
      <p className="newini-hint">{folderLine(pkg)}</p>
      <h2 className="newini-head">WORKFLOWS · WHAT WILL RUN, ONE AFTER ANOTHER</h2>
      <table className="newini-sequence" data-testid="newini-sequence">
        <tbody>
          {bands.map((band) => [
            <tr key={`b${band.n}`} data-band="workflow">
              <td>{band.n}</td>
              <td>{band.workflow}</td>
              <td>{band.templateRef}</td>
              <td>{band.typeWord}</td>
            </tr>,
            ...band.rows.map((row) => (
              <tr key={`r${row.n}`} className="newini-step">
                <td>{row.n}</td>
                <td>{row.name}</td>
                <td>{row.kind}</td>
                <td>{row.agent}</td>
              </tr>
            )),
            band.defaultsLine === null ? null : (
              <tr key={`d${band.n}`} className="newini-defaults">
                <td colSpan={4}>{band.defaultsLine}</td>
              </tr>
            ),
          ])}
        </tbody>
      </table>
    </div>
  );
}
