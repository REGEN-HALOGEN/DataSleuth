import { useState, type FormEvent } from "react";
import { auth, AuthError, type Account } from "./api";

export function SignIn({ onSignIn }: { onSignIn: (account: Account) => void }) {
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
