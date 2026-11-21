import { useState, type FormEvent } from "react";
import { auth, AuthError, type SessionAccount } from "./api";

export function SignIn({
  onSignIn,
}: {
  onSignIn: (account: SessionAccount) => void;
}) {
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    setError("");
    setPending(true);
    try {
      onSignIn(
        await auth.login(
          String(data.get("username")),
          String(data.get("password")),
          String(data.get("organisation") ?? "").trim() || undefined,
        ),
      );
    } catch (failure) {
      form.reset();
      if (failure instanceof AuthError && failure.status === 401) {
        setError("Invalid username or password.");
      } else if (failure instanceof AuthError && failure.status === 429) {
        setError("Too many sign-in attempts. Try again in a minute.");
      } else {
        setError("Sign-in is unavailable. Try again.");
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="sign-in">
      <section className="notice sign-in-panel" aria-labelledby="sign-in-title">
        <div className="brand">
          <span className="mark" aria-hidden="true">
            D
          </span>{" "}
          DataSleuth
        </div>
        <h1 id="sign-in-title">Sign in</h1>
        <form onSubmit={submit}>
          <label htmlFor="username">Username</label>
          <input
            id="username"
            name="username"
            autoComplete="username"
            required
            maxLength={64}
          />
          <label htmlFor="password">Password</label>
          <input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            required
            maxLength={256}
          />
          <details>
            <summary>Sign in to another organisation</summary>
            <label htmlFor="organisation">Organisation ID</label>
            <input id="organisation" name="organisation" maxLength={36} />
          </details>
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          <button type="submit" className="primary" disabled={pending}>
            {pending ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </section>
    </main>
  );
}
