import { Link } from "react-router";
import { categoryLabels, pageSize, reviewLabels, type Finding } from "./api";

export function FindingTable({ rows }: { rows: Finding[] }) {
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th scope="col">Category</th>
            <th scope="col">Evidence</th>
            <th scope="col">Source file</th>
            <th scope="col">Location</th>
            <th scope="col">Confidence</th>
            <th scope="col">Review status</th>
            <th scope="col">Scan submitted</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((finding) => (
            <tr key={finding.id}>
              <th scope="row">
                <Link to={`/discoveries/${finding.id}`}>
                  {categoryLabels[finding.category]}
                </Link>
              </th>
              <td>{finding.masked_evidence}</td>
              <td>
                {finding.relative_path}
                <small>{finding.source_name}</small>
              </td>
              <td>{finding.location}</td>
              <td>{Math.round(finding.confidence * 100)}%</td>
              <td>{reviewLabels[finding.review_status]}</td>
              <td>
                <time dateTime={finding.scan_submitted_at}>
                  {new Date(finding.scan_submitted_at).toLocaleString()}
                </time>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Pagination({
  total,
  offset,
  count,
  onChange,
}: {
  total: number;
  offset: number;
  count: number;
  onChange: (offset: number) => void;
}) {
  if (total <= pageSize && offset === 0) return null;
  return (
    <nav className="row-actions pagination" aria-label="Result pages">
      <button
        disabled={offset === 0}
        onClick={() => onChange(Math.max(0, offset - pageSize))}
      >
        Previous
      </button>
      <span>
        {count
          ? `${offset + 1}–${offset + count} of ${total}`
          : `${total} results`}
      </span>
      <button
        disabled={offset + count >= total || count === 0}
        onClick={() => onChange(offset + pageSize)}
      >
        Next
      </button>
    </nav>
  );
}
