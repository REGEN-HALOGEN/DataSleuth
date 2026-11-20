import type { ScanSource } from "../scans/api";
import { categoryLabels, reviewLabels } from "./api";

export function findingFormValues(
  form: HTMLFormElement,
): Record<string, string> {
  return Object.fromEntries(
    [...new FormData(form)].flatMap(([key, value]) =>
      typeof value === "string" && value.trim() ? [[key, value.trim()]] : [],
    ),
  );
}

export function FindingScopeFields({
  sources,
  defaults,
}: {
  sources: ScanSource[];
  defaults?: Record<string, string>;
}) {
  return (
    <>
      <label>
        Category
        <select name="category" defaultValue={defaults?.category ?? ""}>
          <option value="">All</option>
          {Object.entries(categoryLabels).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <label>
        Source
        <select name="source_id">
          <option value="">All</option>
          {sources.map((source) => (
            <option key={source.id} value={source.id}>
              {source.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        File type
        <select name="extension">
          <option value="">All</option>
          {["txt", "log", "csv", "json", "pdf", "xlsx", "xlsm"].map(
            (extension) => (
              <option key={extension} value={extension}>
                {extension.toUpperCase()}
              </option>
            ),
          )}
        </select>
      </label>
      <label>
        Confidence
        <select name="min_confidence">
          <option value="">Any</option>
          <option value="0.75">75% or higher</option>
          <option value="0.9">90% or higher</option>
        </select>
      </label>
      <label>
        Review status
        <select
          name="review_status"
          defaultValue={defaults?.review_status ?? ""}
        >
          <option value="">All</option>
          {Object.entries(reviewLabels).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <label>
        Scan from (UTC)
        <input name="scan_from" type="date" />
      </label>
      <label>
        Scan to (UTC)
        <input name="scan_to" type="date" />
      </label>
    </>
  );
}
