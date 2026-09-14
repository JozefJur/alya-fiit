import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import type { FormEvent } from "react";

import { ErrorMessage } from "../components/common";
import { homeFor, useAuth } from "../hooks/useAuth";

const DEMO_ACCOUNTS = [
  ["customer1@alya.test", "Customer123!", "Customer"],
  ["warehouse@alya.test", "Warehouse123!", "Warehouse"],
  ["support@alya.test", "Support123!", "Support"],
  ["admin@alya.test", "Admin123!", "Administrator"],
] as const;

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation() as { state?: { from?: string } };
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const user = await login(email, password);
      navigate(location.state?.from ?? homeFor(user.role), { replace: true });
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-page">
      <form className="card login-card" onSubmit={submit} data-testid="login-form">
        <h1>Sign in</h1>
        <ErrorMessage error={error} />
        <label>
          E-mail
          <input
            type="text"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="username"
            data-testid="login-email"
            required
          />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            data-testid="login-password"
            required
          />
        </label>
        <button type="submit" disabled={busy} data-testid="login-submit">
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
      <div className="card login-hint">
        <h2>Local test accounts</h2>
        <table>
          <tbody>
            {DEMO_ACCOUNTS.map(([mail, pass, label]) => (
              <tr key={mail}>
                <td>{label}</td>
                <td>
                  <button
                    type="button"
                    className="linklike"
                    onClick={() => {
                      setEmail(mail);
                      setPassword(pass);
                    }}
                    data-testid={`demo-${label.toLowerCase()}`}
                  >
                    {mail}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted">Seed data only — nothing here is real.</p>
      </div>
    </div>
  );
}
