import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router";
import { ApiError } from "../../lib/api";
import {
  categoryLabels,
  findings,
  reviewLabels,
  type Finding,
  type FindingDetail,
  type ReviewStatus,
} from "./api";
import { FindingTable, Pagination } from "./FindingTable";

export function DiscoveryDetail({
  id,
  onExpired,
}: {
  id: string;
  onExpired: () => void;
}) {
  const [detail, setDetail] = useState<FindingDetail>();
  const [related, setRelated] = useState<{ items: Finding[]; total: number }>();
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState("");
  const [relatedError, setRelatedError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [relatedAttempt, setRelatedAttempt] = useState(0);
  const [review, setReview] = useState<ReviewStatus>("needs_review");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let active = true;
    findings.detail(id).then(
      (value) => {
        if (active) {
          setDetail(value);
          setReview(value.review_status);
        }
      },
      (failure: unknown) => {
        if (!active) return;
        if (failure instanceof ApiError && failure.status === 401) onExpired();
        else
          setError(
            failure instanceof ApiError && failure.status === 404
              ? "This discovery could not be found."
              : "The discovery could not be loaded.",
          );
      },
    );
    return () => {
      active = false;
    };
  }, [id, attempt, onExpired]);

  useEffect(() => {
    let active = true;
    findings.related(id, offset).then(
      (value) => {
        if (active) setRelated(value);
      },
      (failure: unknown) => {
        if (!active) return;
        if (failure instanceof ApiError && failure.status === 401) onExpired();
        else setRelatedError(true);
      },
    );
    return () => {
      active = false;
    };
  }, [id, offset, relatedAttempt, onExpired]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      await findings.review(id, review);
      setDetail(await findings.detail(id));
    } catch (failure) {
      if (failure instanceof ApiError && failure.status === 401) onExpired();
      else setError("The review status could not be refreshed. Try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <p>
        <Link to="/discoveries">Back to Discoveries</Link>
      </p>
      {error && (
        <div role="alert">
          <p className="form-error">{error}</p>
          {!detail && (
            <button
              onClick={() => {
                setError("");
                setAttempt(attempt + 1);
              }}
            >
              Try again
            </button>
          )}
        </div>
      )}
      {!detail ? (
        !error && <p role="status">Loading discovery…</p>
      ) : (
        <>
          <h1>Potential {categoryLabels[detail.category]} match</h1>
          <dl className="finding-details">
            <dt>Evidence</dt>
            <dd>{detail.masked_evidence}</dd>
            <dt>Source</dt>
            <dd>{detail.source_name}</dd>
            <dt>Relative file path</dt>
            <dd>{detail.relative_path}</dd>
            <dt>File size</dt>
            <dd>
              {detail.size_bytes === null
                ? "Unavailable"
                : `${detail.size_bytes.toLocaleString()} bytes`}
            </dd>
            <dt>Location</dt>
            <dd>Extracted text line {detail.location}</dd>
            <dt>Detector</dt>
            <dd>
              {categoryLabels[detail.category]} · version{" "}
              {detail.detector_version}
            </dd>
            <dt>Confidence</dt>
            <dd>{Math.round(detail.confidence * 100)}%</dd>
            <dt>Scan</dt>
            <dd>
              <Link to={`/discoveries?scan=${detail.scan_id}`}>
                View findings from this scan
              </Link>
            </dd>
          </dl>
          <section className="notice">
            <h2>Review</h2>
            <form className="row-actions" onSubmit={submit}>
              <label htmlFor="finding-status">Review status</label>
              <select
                id="finding-status"
                value={review}
                onChange={(event) =>
                  setReview(event.target.value as ReviewStatus)
                }
              >
                {Object.entries(reviewLabels).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
              <button
                className="primary"
                type="submit"
                disabled={saving || detail.review_status === review}
              >
                Save review
              </button>
            </form>
            {detail.history.length > 0 && (
              <ul aria-label="Review history">
                {detail.history.map((entry, index) => (
                  <li key={`${entry.reviewed_at}-${index}`}>
                    {reviewLabels[entry.status]} by {entry.reviewer} ·{" "}
                    <time dateTime={entry.reviewed_at}>
                      {new Date(entry.reviewed_at).toLocaleString()}
                    </time>
                  </li>
                ))}
              </ul>
            )}
          </section>
          <section className="related-occurrences">
            <h2>Related occurrences ({detail.related_count})</h2>
            <p>
              A match indicates the same normalized value. It does not establish
              a shared identity or a data transfer.
            </p>
            {relatedError ? (
              <div role="alert">
                <p>Related occurrences could not be loaded.</p>
                <button
                  onClick={() => {
                    setRelatedError(false);
                    setRelatedAttempt(relatedAttempt + 1);
                  }}
                >
                  Try again
                </button>
              </div>
            ) : !related ? (
              <p role="status">Loading related occurrences…</p>
            ) : related.items.length ? (
              <>
                <FindingTable rows={related.items} />
                <Pagination
                  total={related.total}
                  count={related.items.length}
                  offset={offset}
                  onChange={(value) => {
                    setRelated(undefined);
                    setOffset(value);
                  }}
                />
              </>
            ) : (
              <p>No other occurrences share this fingerprint.</p>
            )}
          </section>
        </>
      )}
    </>
  );
}
