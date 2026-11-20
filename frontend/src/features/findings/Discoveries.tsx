import { useEffect, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router";
import { ApiError } from "../../lib/api";
import { scans, type ScanSource } from "../scans/api";
import {
  categoryLabels,
  findings,
  pageSize,
  reviewLabels,
  type Finding,
} from "./api";
import { FindingScopeFields, findingFormValues } from "./FindingScopeFields";
import { FindingTable, Pagination } from "./FindingTable";

export function Discoveries({ onExpired }: { onExpired: () => void }) {
  const [search] = useSearchParams();
  const scanId = search.get("scan");
  const [sources, setSources] = useState<ScanSource[]>([]);
  const [filters, setFilters] = useState<Record<string, string>>(() => {
    const initial: Record<string, string> = {};
    const review = search.get("review");
    const category = search.get("category");
    if (review && Object.hasOwn(reviewLabels, review))
      initial.review_status = review;
    if (category && Object.hasOwn(categoryLabels, category))
      initial.category = category;
    return initial;
  });
  const [offset, setOffset] = useState(0);
  const [results, setResults] = useState<{ items: Finding[]; total: number }>();
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    scans.sources().then(
      (value) => {
        if (active) setSources(value);
      },
      () => {},
    );
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    findings
      .search({
        ...filters,
        ...(scanId ? { scan_id: scanId } : {}),
        offset,
        limit: pageSize,
      })
      .then(
        (value) => {
          if (active) setResults(value);
        },
        (failure: unknown) => {
          if (!active) return;
          if (failure instanceof ApiError && failure.status === 401)
            onExpired();
          else setError(true);
        },
      );
    return () => {
      active = false;
    };
  }, [scanId, filters, offset, attempt, onExpired]);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setResults(undefined);
    setError(false);
    setOffset(0);
    setFilters(findingFormValues(event.currentTarget));
  }

  return (
    <>
      <div className="overview-heading">
        <h1>Discoveries</h1>
        <Link
          to={
            scanId ? `/reports?scan=${encodeURIComponent(scanId)}` : "/reports"
          }
        >
          {scanId ? "Export this scan" : "Reports"}
        </Link>
      </div>
      <form className="finding-filters" onSubmit={submit}>
        <label>
          Search file or source
          <input name="term" type="search" maxLength={160} />
        </label>
        <FindingScopeFields sources={sources} defaults={filters} />
        <button className="primary" type="submit">
          Apply filters
        </button>
      </form>
      {error ? (
        <div role="alert">
          <p>Discoveries could not be loaded.</p>
          <button
            onClick={() => {
              setError(false);
              setAttempt(attempt + 1);
            }}
          >
            Try again
          </button>
        </div>
      ) : !results ? (
        <p role="status">Loading discoveries…</p>
      ) : (
        <>
          {results.items.length ? (
            <FindingTable rows={results.items} />
          ) : (
            <p>No findings match these filters.</p>
          )}
          <Pagination
            total={results.total}
            offset={offset}
            count={results.items.length}
            onChange={(value) => {
              setResults(undefined);
              setOffset(value);
            }}
          />
        </>
      )}
    </>
  );
}
