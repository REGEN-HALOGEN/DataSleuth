import { useEffect, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router";
import { ApiError, fetchApi, jsonRequest } from "../../lib/api";
import {
  FindingScopeFields,
  findingFormValues,
} from "../findings/FindingScopeFields";
import { scans, type Scan, type ScanSource } from "../scans/api";

export function Reports({ onExpired }: { onExpired: () => void }) {
  const [query] = useSearchParams();
  const scanId = query.get("scan");
  const [choices, setChoices] = useState<{
    jobs: Scan[];
    sources: ScanSource[];
  }>();
  const [error, setError] = useState("");
  const [loadFailed, setLoadFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    Promise.all([scans.history(), scans.sources()]).then(
      ([jobs, sources]) => {
        if (active) setChoices({ jobs, sources });
      },
      (failure: unknown) => {
        if (!active) return;
        if (failure instanceof ApiError && failure.status === 401) onExpired();
        else setLoadFailed(true);
      },
    );
    return () => {
      active = false;
    };
  }, [attempt, onExpired]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const { format = "csv", ...filters } = findingFormValues(
      event.currentTarget,
    );
    setError("");
    setSaved(false);
    if (
      filters.scan_from &&
      filters.scan_to &&
      filters.scan_from > filters.scan_to
    ) {
      setError("Choose a start date on or before the end date.");
      return;
    }
    setBusy(true);
    try {
      const response = await fetchApi(
        `reports/findings.${format}`,
        jsonRequest("POST", filters),
      );
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = `datasleuth-findings.${format}`;
      document.body.append(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      setSaved(true);
    } catch (failure) {
      if (failure instanceof ApiError && failure.status === 401) onExpired();
      else if (failure instanceof ApiError && failure.status === 422)
        setError(
          "Check the filters and narrow the report to at most 10,000 findings.",
        );
      else setError("The report could not be downloaded. Try again.");
    } finally {
      setBusy(false);
    }
  }

  const names = new Map(
    choices?.sources.map((source) => [source.id, source.name]),
  );

  return (
    <>
      <h1>Reports</h1>
      <section className="notice" aria-labelledby="report-fields">
        <h2 id="report-fields">Masked findings export</h2>
        <p>
          Each report includes its ID, generation time, scope, filters, and row
          count. Each finding includes IDs for the finding, source, scan, and
          file, along with scan submission time, file size, category, detector
          version, confidence, extracted text location, review status and time,
          and masked evidence.
        </p>
      </section>
      {loadFailed ? (
        <div role="alert">
          <p>Report options could not be loaded.</p>
          <button
            onClick={() => {
              setLoadFailed(false);
              setAttempt(attempt + 1);
            }}
          >
            Try again
          </button>
        </div>
      ) : !choices ? (
        <p role="status">Loading report options…</p>
      ) : (
        <form className="finding-filters" onSubmit={submit}>
          <label>
            Scan
            <select name="scan_id" defaultValue={scanId ?? ""}>
              <option value="">All scans</option>
              {scanId && !choices.jobs.some((job) => job.id === scanId) && (
                <option value={scanId}>Selected scan</option>
              )}
              {choices.jobs.map((job) => (
                <option key={job.id} value={job.id}>
                  {names.get(job.source_id) ?? "Local source"} ·{" "}
                  {new Date(job.started_at).toLocaleString()}
                </option>
              ))}
            </select>
          </label>
          <FindingScopeFields sources={choices.sources} />
          <label>
            Format
            <select name="format">
              <option value="csv">CSV</option>
              <option value="json">JSON</option>
            </select>
          </label>
          <button className="primary" type="submit" disabled={busy}>
            {busy ? "Preparing report…" : "Download report"}
          </button>
        </form>
      )}
      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}
      {saved && <p role="status">Report download started.</p>}
    </>
  );
}
