import { useEffect, useState } from "react";
import { Link } from "react-router";
import { ApiError, request } from "../../lib/api";
import { categoryLabels } from "../findings/api";
import { scanStatusLabels, type Scan } from "./api";

type OverviewData = {
  sources: number;
  scans: number;
  files_processed: number;
  findings_awaiting_review: number;
  recent_scans: (Pick<
    Scan,
    "id" | "status" | "started_at" | "files_processed" | "findings_created"
  > & { source_name: string })[];
  categories: { category: keyof typeof categoryLabels; count: number }[];
};

export function Overview({ onExpired }: { onExpired: () => void }) {
  const [summary, setSummary] = useState<OverviewData>();
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    request<OverviewData>("overview").then(
      (value) => {
        if (active) setSummary(value);
      },
      (failure: unknown) => {
        if (!active) return;
        if (failure instanceof ApiError && failure.status === 401) onExpired();
        else setError(true);
      },
    );
    return () => {
      active = false;
    };
  }, [attempt, onExpired]);

  return (
    <>
      <div className="overview-heading">
        <h1>Overview</h1>
        <Link to="/sources">Start a scan</Link>
      </div>
      {error ? (
        <div role="alert">
          <p>Overview could not be loaded.</p>
          <button
            onClick={() => {
              setError(false);
              setAttempt(attempt + 1);
            }}
          >
            Try again
          </button>
        </div>
      ) : !summary ? (
        <p role="status">Loading overview…</p>
      ) : (
        <>
          <dl className="overview-metrics">
            <div>
              <dt>Scan sources</dt>
              <dd>{summary.sources.toLocaleString()}</dd>
            </div>
            <div>
              <dt>Scans</dt>
              <dd>{summary.scans.toLocaleString()}</dd>
            </div>
            <div>
              <dt>Files processed</dt>
              <dd>{summary.files_processed.toLocaleString()}</dd>
            </div>
            <div>
              <dt>Awaiting review</dt>
              <dd>
                <Link
                  aria-label="View findings awaiting review"
                  to="/discoveries?review=needs_review"
                >
                  {summary.findings_awaiting_review.toLocaleString()}
                </Link>
              </dd>
            </div>
          </dl>
          <section aria-labelledby="recent-scans">
            <h2 id="recent-scans">Recent scans</h2>
            {summary.recent_scans.length === 0 ? (
              <p>No scans have run yet.</p>
            ) : (
              <>
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th scope="col">Source</th>
                        <th scope="col">Submitted</th>
                        <th scope="col">Status</th>
                        <th scope="col">Processed</th>
                        <th scope="col">Findings</th>
                      </tr>
                    </thead>
                    <tbody>
                      {summary.recent_scans.map((scan) => (
                        <tr key={scan.id}>
                          <th scope="row">{scan.source_name}</th>
                          <td>
                            <time dateTime={scan.started_at}>
                              {new Date(scan.started_at).toLocaleString()}
                            </time>
                          </td>
                          <td>{scanStatusLabels[scan.status]}</td>
                          <td>{scan.files_processed}</td>
                          <td>
                            {scan.findings_created > 0 ? (
                              <Link to={`/discoveries?scan=${scan.id}`}>
                                {scan.findings_created}
                              </Link>
                            ) : (
                              0
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p>
                  <Link to="/scans">View scan history</Link>
                </p>
              </>
            )}
          </section>
          {summary.categories.length > 0 && (
            <section aria-labelledby="finding-categories">
              <h2 id="finding-categories">Findings by category</h2>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th scope="col">Category</th>
                      <th scope="col">Findings</th>
                    </tr>
                  </thead>
                  <tbody>
                    {summary.categories.map(({ category, count }) => (
                      <tr key={category}>
                        <th scope="row">
                          <Link to={`/discoveries?category=${category}`}>
                            {categoryLabels[category]}
                          </Link>
                        </th>
                        <td>{count.toLocaleString()}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}
        </>
      )}
    </>
  );
}
