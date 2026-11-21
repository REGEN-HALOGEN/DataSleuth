import { useEffect, useState, type FormEvent } from "react";
import { ApiError, jsonRequest, request } from "../../lib/api";
import type { ScanSource } from "./api";

type Capabilities = {
  enabled: boolean;
  max_bytes: number;
  media_types: Record<string, string>;
};

export function UploadDocument({
  onSource,
  onExpired,
}: {
  onSource: (source: ScanSource) => void;
  onExpired: () => void;
}) {
  const [capabilities, setCapabilities] = useState<Capabilities>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    request<Capabilities>("documents/capabilities").then(
      (result) => {
        if (active) setCapabilities(result);
      },
      (failure) => {
        if (!active) return;
        if (failure instanceof ApiError && failure.status === 401) onExpired();
        else setError("Upload settings could not be loaded.");
      },
    );
    return () => {
      active = false;
    };
  }, [onExpired]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!capabilities?.enabled || busy) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    const file = data.get("document");
    const ext =
      file instanceof File
        ? file.name.match(/\.[^.]+$/)?.[0].toLowerCase()
        : undefined;
    if (
      !(file instanceof File) ||
      !ext ||
      !capabilities.media_types[ext] ||
      !file.size ||
      file.size > capabilities.max_bytes
    ) {
      setError("Choose a supported document within the displayed size limit.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const reservation = await request<ScanSource>(
        "documents",
        jsonRequest("POST", {
          name: String(data.get("label")),
          size_bytes: file.size,
          extension: ext,
        }),
      );
      onSource(reservation);
      const ready = await request<ScanSource>(
        `documents/${reservation.id}/content`,
        {
          method: "PUT",
          headers: { "Content-Type": capabilities.media_types[ext] },
          body: file,
        },
      );
      onSource(ready);
      form.reset();
    } catch (failure) {
      if (failure instanceof ApiError && failure.status === 401) onExpired();
      else
        setError(
          "Upload could not be confirmed. Refresh the source list to check its status.",
        );
    } finally {
      setBusy(false);
    }
  }

  if (!capabilities?.enabled) return error ? <p role="alert">{error}</p> : null;
  return (
    <form className="notice source-form" onSubmit={submit}>
      <h2>Upload a private document</h2>
      <label htmlFor="upload-name">Document label</label>
      <input id="upload-name" name="label" required maxLength={128} />
      <label htmlFor="upload-file">Document</label>
      <input
        id="upload-file"
        name="document"
        type="file"
        required
        accept={Object.keys(capabilities.media_types).join(",")}
      />
      <p>
        Maximum file size {(capabilities.max_bytes / 1048576).toLocaleString()}{" "}
        MiB. Uploading makes the document available for a separate scan.
      </p>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <button className="primary" type="submit" disabled={busy}>
        {busy ? "Uploading…" : "Upload document"}
      </button>
    </form>
  );
}
