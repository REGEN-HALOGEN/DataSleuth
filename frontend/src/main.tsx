import { StrictMode, useCallback, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  BrowserRouter,
  Link,
  Navigate,
  NavLink,
  Outlet,
  Route,
  Routes,
  useLocation,
  useMatch,
} from "react-router";
import { Accounts } from "./features/auth/Accounts";
import { auth, AuthError, type Account } from "./features/auth/api";
import { SignIn } from "./features/auth/SignIn";
import { ScanHistory } from "./features/scans/ScanHistory";
import { ScanSources } from "./features/scans/ScanSources";
import { Discoveries } from "./features/findings/Discoveries";
import { DiscoveryDetail } from "./features/findings/DiscoveryDetail";
import "./styles/main.css";

const discoveryPath = /^\/discoveries\/[0-9a-f-]{36}$/i;

const pageTitles: Record<string, string> = {
  "/": "Overview",
  "/accounts": "Accounts",
  "/sources": "Scan Sources",
  "/discoveries": "Discoveries",
  "/scans": "Scan History",
};

function Shell({
  account,
  onExpired,
}: {
  account: Account;
  onExpired: () => void;
}) {
  const [signingOut, setSigningOut] = useState(false);
  const [error, setError] = useState("");
  const location = useLocation();

  async function logout() {
    setSigningOut(true);
    setError("");
    try {
      await auth.logout();
      onExpired();
    } catch {
      setError("Sign-out could not be confirmed. Try again.");
    } finally {
      setSigningOut(false);
    }
  }

  return (
    <div className="shell">
      <aside className="sidebar" aria-label="Product">
        <div className="brand">
          <span className="mark" aria-hidden="true">
            D
          </span>{" "}
          DataSleuth
        </div>
        <nav aria-label="Main navigation">
          <NavLink to="/" end>
            Overview
          </NavLink>
          {account.role !== "viewer" && (
            <>
              <NavLink to="/discoveries">Discoveries</NavLink>
              <NavLink to="/sources">Scan Sources</NavLink>
              <NavLink to="/scans">Scan History</NavLink>
            </>
          )}
          {account.role === "admin" && (
            <NavLink to="/accounts">Accounts</NavLink>
          )}
        </nav>
      </aside>
      <main>
        <header className="topbar">
          <strong>
            {pageTitles[location.pathname] ??
              (discoveryPath.test(location.pathname)
                ? "Discoveries"
                : "Overview")}
          </strong>
          <div className="account-controls">
            <span>{account.username}</span>
            <button onClick={logout} disabled={signingOut}>
              {signingOut ? "Signing out…" : "Sign out"}
            </button>
          </div>
        </header>
        <section className="content">
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          <Outlet />
        </section>
      </main>
    </div>
  );
}

function App() {
  const [account, setAccount] = useState<Account | null>();
  const [unavailable, setUnavailable] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const expire = useCallback(() => setAccount(null), []);
  const discoveryId = useMatch("/discoveries/:id")?.params.id;
  const location = useLocation();

  useEffect(() => {
    let active = true;
    auth.current().then(
      (result) => {
        if (active) setAccount(result);
      },
      (failure: unknown) => {
        if (!active) return;
        if (failure instanceof AuthError && failure.status === 401) expire();
        else setUnavailable(true);
      },
    );
    return () => {
      active = false;
    };
  }, [attempt, expire]);

  useEffect(() => {
    if (!account) return;
    let active = true;
    function checkSession() {
      auth.current().then(
        (result) => {
          if (
            active &&
            (result.id !== account?.id || result.role !== account.role)
          )
            setAccount(result);
        },
        (failure: unknown) => {
          if (active && failure instanceof AuthError && failure.status === 401)
            expire();
        },
      );
    }
    window.addEventListener("focus", checkSession);
    const timer = window.setInterval(checkSession, 60_000);
    return () => {
      active = false;
      window.removeEventListener("focus", checkSession);
      window.clearInterval(timer);
    };
  }, [account, expire]);

  if (unavailable)
    return (
      <main className="content">
        <p role="alert">Your session could not be checked.</p>
        <button
          onClick={() => {
            setUnavailable(false);
            setAttempt(attempt + 1);
          }}
        >
          Try again
        </button>
      </main>
    );
  if (account === undefined)
    return (
      <main className="content" role="status">
        Checking session…
      </main>
    );

  const returnPath: unknown = location.state?.from;
  const requestedPath =
    typeof returnPath === "string" &&
    (Object.hasOwn(pageTitles, returnPath) || discoveryPath.test(returnPath))
      ? returnPath
      : "/";
  const canScan = account?.role === "admin" || account?.role === "analyst";

  return (
    <Routes>
      <Route
        path="/sign-in"
        element={
          account ? (
            <Navigate to={requestedPath} replace />
          ) : (
            <SignIn onSignIn={setAccount} />
          )
        }
      />
      <Route
        element={
          account ? (
            <Shell account={account} onExpired={expire} />
          ) : (
            <Navigate
              to="/sign-in"
              replace
              state={{ from: location.pathname }}
            />
          )
        }
      >
        <Route
          index
          element={
            <>
              <h1>Overview</h1>
              <div className="notice">
                <h2>Local scans</h2>
                {canScan ? (
                  <p>
                    <Link to="/sources">Choose an approved directory</Link> or{" "}
                    <Link to="/scans">view scan history</Link>.
                  </p>
                ) : (
                  <p>
                    An administrator or analyst account is required to manage
                    scans.
                  </p>
                )}
              </div>
            </>
          }
        />
        <Route
          path="discoveries"
          element={
            canScan ? (
              <Discoveries onExpired={expire} />
            ) : (
              <>
                <h1>Discoveries</h1>
                <p role="alert">Operator access is required.</p>
              </>
            )
          }
        />
        <Route
          path="discoveries/:id"
          element={
            canScan ? (
              discoveryId && discoveryPath.test(location.pathname) ? (
                <DiscoveryDetail
                  key={discoveryId}
                  id={discoveryId}
                  onExpired={expire}
                />
              ) : (
                <p role="alert">This discovery could not be found.</p>
              )
            ) : (
              <>
                <h1>Discoveries</h1>
                <p role="alert">Operator access is required.</p>
              </>
            )
          }
        />
        <Route
          path="sources"
          element={
            canScan ? (
              <ScanSources onExpired={expire} />
            ) : (
              <>
                <h1>Scan Sources</h1>
                <p role="alert">Operator access is required.</p>
              </>
            )
          }
        />
        <Route
          path="scans"
          element={
            canScan ? (
              <ScanHistory onExpired={expire} />
            ) : (
              <>
                <h1>Scan History</h1>
                <p role="alert">Operator access is required.</p>
              </>
            )
          }
        />
        <Route
          path="accounts"
          element={
            account?.role === "admin" ? (
              <Accounts onExpired={expire} />
            ) : (
              <>
                <h1>Accounts</h1>
                <p role="alert">Administrator access is required.</p>
              </>
            )
          }
        />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
);
