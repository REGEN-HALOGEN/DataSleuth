import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router";
import { ApiError } from "../../lib/api";
import { UploadDocument } from "./UploadDocument";
import { scans, type ScanSource } from "./api";

export function ScanSources({ onExpired }: { onExpired: () => void }) {
  const [sources, setSources] = useState<ScanSource[]>();
  const [loadError, setLoadError] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState<ScanSource>();
  const [confirming, setConfirming] = useState<ScanSource>();
  const [attempt, setAttempt] = useState(0);
  const navigate = useNavigate();

  useEffect(() => {
    let active = true;
    scans.sources().then(
      (result) => {
        if (active) setSources(result);
      },
      (failure: unknown) => {
        if (!active) return;
        if (failure instanceof ApiError && failure.status === 401) onExpired();
        else setLoadError(true);
      },
    );
    return () => {
      active = false;
    };
  }, [attempt, onExpired]);

  async function mutate(action: () => Promise<unknown>, message: string) {
    setError("");
    setBusy(true);
    try {
      await action();
    } catch (failure) {
      if (failure instanceof ApiError && failure.status === 401) onExpired();
      else if (failure instanceof ApiError && failure.status === 403)
        setError("Operator access is required.");
      else if (failure instanceof ApiError && failure.status === 422)
        setError(
          "Enter a valid name and an existing absolute directory within an approved scan root.",
        );
      else setError(message);
    } finally {
      setBusy(false);
    }
  }

  function applySource(updated: ScanSource) {
    setSources((current) =>
      [
        ...(current ?? []).filter((source) => source.id !== updated.id),
        updated,
      ].sort((left, right) => left.name.localeCompare(right.name)),
    );
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const name = String(data.get("name"));
    await mutate(async () => {
      const saved = editing
        ? await scans.updateSource(editing.id, { name })
        : await scans.createSource(name, String(data.get("path")));
      applySource(saved);
      setEditing(undefined);
      form.reset();
    }, "The source could not be saved. Check whether this directory is already registered.");
  }

  return (
    <>
      <h1>Scan Sources</h1>
      <form
        key={editing?.id ?? "create"}
        className="notice source-form"
        onSubmit={submit}
      >
        <h2>{editing ? "Rename source" : "Add a source"}</h2>
        <label htmlFor="source-name">Source name</label>
        <input
          id="source-name"
          name="name"
          defaultValue={editing?.name}
          maxLength={128}
          required
        />
        {!editing && (
          <>
            <label htmlFor="source-path">Directory path</label>
            <input
              id="source-path"
              name="path"
              aria-describedby="source-path-help"
              maxLength={4096}
              required
            />
            <p id="source-path-help">
              Enter an absolute path on the server within an approved scan root.
            </p>
          </>
        )}
        <div className="row-actions">
          <button className="primary" disabled={busy || !sources} type="submit">
            {editing ? "Save name" : "Add source"}
          </button>
          {editing && (
            <button
              disabled={busy}
              type="button"
              onClick={() => setEditing(undefined)}
            >
              Cancel
            </button>
          )}
        </div>
      </form>
      <UploadDocument onSource={applySource} onExpired={onExpired} />
      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}
      {confirming && (
        <section
          className="notice scan-confirmation"
          aria-labelledby="scan-confirm-title"
        >
          <h2 id="scan-confirm-title">Start a read-only scan</h2>
          <p>
            DataSleuth will scan {confirming.name} for potential personal data
            in TXT, LOG, CSV, JSON, PDF, XLSX, and XLSM files. Scan limits and
            exclusions apply.
          </p>
          <div className="row-actions">
            <button
              className="primary"
              disabled={busy}
              onClick={() =>
                void mutate(async () => {
                  await scans.start(confirming.id);
                  navigate("/scans");
                }, "The scan could not start. Check that the source is enabled and has no active scan.")
              }
            >
              Confirm and start
            </button>
            <button disabled={busy} onClick={() => setConfirming(undefined)}>
              Back
            </button>
          </div>
        </section>
      )}
      {loadError ? (
        <div role="alert">
          <p>Scan sources could not be loaded.</p>
          <button
            onClick={() => {
              setLoadError(false);
              setAttempt(attempt + 1);
            }}
          >
            Try again
          </button>
        </div>
      ) : !sources ? (
        <p role="status">Loading scan sources…</p>
      ) : sources.length === 0 ? (
        <p>No sources yet. Add an approved directory to start a scan.</p>
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th scope="col">Source</th>
                <th scope="col">Location</th>
                <th scope="col">Status</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {sources.map((source) => (
                <tr key={source.id}>
                  <th scope="row">{source.name}</th>
                  <td>
                    {source.configured_path ?? "Private storage"}
                    {source.upload_state === "ready" && source.expires_at && (
                      <div>
                        Expires {new Date(source.expires_at).toLocaleString()}
                      </div>
                    )}
                  </td>
                  <td>
                    {source.upload_state && source.upload_state !== "ready"
                      ? {
                          pending: "Awaiting upload",
                          deleting: "Deletion requested",
                          deleted: "Document deleted",
                        }[source.upload_state]
                      : source.enabled
                        ? "Enabled"
                        : "Disabled"}
                  </td>
                  <td>
                    <div className="row-actions">
                      <button
                        disabled={!source.enabled || busy}
                        onClick={() => {
                          setError("");
                          setConfirming(source);
                        }}
                      >
                        Start scan
                      </button>
                      <button
                        disabled={busy}
                        onClick={() => {
                          setError("");
                          setEditing(source);
                        }}
                      >
                        Rename
                      </button>
                      {(!source.upload_state ||
                        source.upload_state === "ready") && (
                        <button
                          disabled={busy}
                          onClick={() =>
                            void mutate(async () => {
                              applySource(
                                await scans.updateSource(source.id, {
                                  enabled: !source.enabled,
                                }),
                              );
                              if (source.id === confirming?.id)
                                setConfirming(undefined);
                            }, "The source status could not be updated.")
                          }
                        >
                          {source.enabled ? "Disable" : "Enable"}
                        </button>
                      )}
                      {(source.upload_state === "pending" ||
                        source.upload_state === "ready") && (
                        <button
                          disabled={busy}
                          onClick={() => {
                            if (
                              window.confirm(
                                "Delete the stored document? Existing findings and scan history will remain available.",
                              )
                            ) {
                              void mutate(
                                async () =>
                                  applySource(
                                    await scans.deleteDocument(source.id),
                                  ),
                                "Deletion could not be requested. Finish or cancel any active scan first.",
                              );
                            }
                          }}
                        >
                          Delete document
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p>
        <Link to="/scans">View scan history</Link>
      </p>
    </>
  );
}
