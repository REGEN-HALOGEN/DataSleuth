import { useEffect, useState } from "react";
import { Link } from "react-router";
import { ApiError } from "../../lib/api";
import { scans, scanStatusLabels, type Scan } from "./api";

const explanations: Record<string, string> = {
  source_unavailable: "The source or operator was no longer available.",
  retry_limit: "The worker retry limit was reached.",
  fingerprint_version_changed:
    "The fingerprint key version changed during the scan.",
};

export function ScanHistory({ onExpired }: { onExpired: () => void }) {
  const [jobs, setJobs] = useState<Scan[]>();
  const [names, setNames] = useState<Record<string, string>>({});
  const [unavailable, setUnavailable] = useState(false);
  const [cancelling, setCancelling] = useState<string>();
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    let next: number | undefined;
    async function refresh() {
      try {
        const results = await scans.history();
        if (!active) return;
        setJobs(results);
        setUnavailable(false);
      } catch (failure) {
        if (!active) return;
        if (failure instanceof ApiError && failure.status === 401) {
          onExpired();
          return;
        }
        setUnavailable(true);
      }
      if (active) next = window.setTimeout(refresh, 2000);
    }
    void refresh();
    scans.sources().then(
      (sources) => {
        if (active)
          setNames(
            Object.fromEntries(
              sources.map((source) => [source.id, source.name]),
            ),
          );
      },
      () => {},
    );
    return () => {
      active = false;
      window.clearTimeout(next);
    };
  }, [attempt, onExpired]);

  async function cancelScan(id: string) {
    setCancelling(id);
    setError("");
    try {
      const update = await scans.cancel(id);
      setJobs((current) =>
        current?.map((job) => (job.id === id ? update : job)),
      );
      setAttempt((value) => value + 1);
    } catch (failure) {
      if (failure instanceof ApiError && failure.status === 401) onExpired();
      else setError("The cancellation could not be confirmed. Try again.");
    } finally {
      setCancelling(undefined);
    }
  }

  return (
    <>
      <h1>Scan History</h1>
      {unavailable && (
        <p role="alert">
          Scan history could not be refreshed. DataSleuth will retry
          automatically.
        </p>
      )}
      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}
      {!jobs ? (
        !unavailable && <p role="status">Loading scans…</p>
      ) : jobs.length === 0 ? (
        <p>
          No scans yet. <Link to="/sources">Choose an approved source</Link> to
          start one.
        </p>
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th scope="col">Source</th>
                <th scope="col">Submitted</th>
                <th scope="col">Status</th>
                <th scope="col">Discovered</th>
                <th scope="col">Processed</th>
                <th scope="col">Skipped</th>
                <th scope="col">Failed</th>
                <th scope="col">Findings</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => (
                <tr key={job.id}>
                  <th scope="row">{names[job.source_id] ?? "Local source"}</th>
                  <td>
                    <time dateTime={job.started_at}>
                      {new Date(job.started_at).toLocaleString()}
                    </time>
                  </td>
                  <td>
                    {job.cancel_requested && job.status === "running"
                      ? "Cancelling"
                      : scanStatusLabels[job.status]}
                    {job.inventory_limited && (
                      <small>Entry limit reached</small>
                    )}
                    {job.error_summary && (
                      <small>
                        {explanations[job.error_summary] ??
                          "The scan could not finish."}
                      </small>
                    )}
                  </td>
                  <td>{job.files_discovered}</td>
                  <td>{job.files_processed}</td>
                  <td>{job.files_skipped}</td>
                  <td>{job.files_failed}</td>
                  <td>
                    {job.findings_created > 0 ? (
                      <Link
                        aria-label={`View ${job.findings_created} findings`}
                        to={`/discoveries?scan=${job.id}`}
                      >
                        {job.findings_created}
                      </Link>
                    ) : (
                      0
                    )}
                  </td>
                  <td>
                    {(job.status === "queued" || job.status === "running") &&
                      !job.cancel_requested && (
                        <button
                          disabled={cancelling !== undefined}
                          onClick={() => void cancelScan(job.id)}
                        >
                          Cancel scan
                        </button>
                      )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {jobs.length === 50 && <p>Showing the latest 50 scans.</p>}
        </div>
      )}
      <p>
        <Link to="/sources">Manage scan sources</Link>
      </p>
    </>
  );
}
