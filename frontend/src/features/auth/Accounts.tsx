import { useEffect, useState } from "react";
import { auth, AuthError, type Account } from "./api";

export function Accounts({ onExpired }: { onExpired: () => void }) {
  const [accounts, setAccounts] = useState<Account[]>();
  const [error, setError] = useState<number>();
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    auth.users().then(
      (result) => {
        if (active) setAccounts(result);
      },
      (failure: unknown) => {
        if (!active) return;
        const status = failure instanceof AuthError ? failure.status : 0;
        if (status === 401) onExpired();
        else setError(status);
      },
    );
    return () => {
      active = false;
    };
  }, [attempt, onExpired]);

  return (
    <>
      <h1>Accounts</h1>
      {error === 403 ? (
        <p role="alert">Administrator access is required.</p>
      ) : error !== undefined ? (
        <div role="alert">
          <p>Accounts could not be loaded.</p>
          <button
            onClick={() => {
              setError(undefined);
              setAttempt(attempt + 1);
            }}
          >
            Try again
          </button>
        </div>
      ) : accounts === undefined ? (
        <p role="status">Loading accounts…</p>
      ) : accounts.length === 0 ? (
        <p>No accounts are available.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th scope="col">Username</th>
              <th scope="col">Role</th>
            </tr>
          </thead>
          <tbody>
            {accounts.map((account) => (
              <tr key={account.id}>
                <td>{account.username}</td>
                <td>{account.role}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
