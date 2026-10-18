"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { ACCOUNTS } from "@/lib/api";
import { useStore } from "@/lib/store";

export default function LoginPage() {
  return <Suspense fallback={null}><Login /></Suspense>;
}

/** Log in, sign up, or use the shared demo account (item 24 step 1). */
function Login() {
  const s = useStore();
  const router = useRouter();
  const params = useSearchParams();
  const next = params.get("next") || "/ask";
  const [mode, setMode] = useState<"login" | "signup">(params.get("mode") === "signup" ? "signup" : "login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (s.account) router.replace(next); }, [s.account, next, router]);

  const go = async (m: "login" | "signup" | "demo") => {
    setErr("");
    setBusy(true);
    try {
      await s.login(m, email, password);
    } catch (e) {
      setErr(String((e as Error).message || e));
    } finally {
      setBusy(false);
    }
  };

  if (!ACCOUNTS) {
    return <div className="auth"><div className="auth-card"><h1>Accounts are off</h1><p className="text-2">This build runs the shared demo company without log-in.</p></div></div>;
  }
  return (
    <div className="auth">
      <div className="auth-card nx-rise">
        <span className="eyebrow">NODUS</span>
        <h1>{mode === "login" ? "Log in to your workspace" : "Create your workspace"}</h1>
        <p className="text-2">Each account gets its own graph. Bring your Slack, Linear, GitHub, Jira or docs, or load the demo company.</p>
        <div className="seg" role="tablist" aria-label="Log in or sign up">
          <button type="button" role="tab" aria-selected={mode === "login"} className={mode === "login" ? "on" : ""} onClick={() => setMode("login")}>Log in</button>
          <button type="button" role="tab" aria-selected={mode === "signup"} className={mode === "signup" ? "on" : ""} onClick={() => setMode("signup")}>Sign up</button>
        </div>
        <form className="stack-3" onSubmit={(e) => { e.preventDefault(); void go(mode); }}>
          <label className="auth-field"><span>Email</span>
            <input type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </label>
          <label className="auth-field"><span>Password</span>
            <input type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} required minLength={mode === "signup" ? 8 : undefined}
              value={password} onChange={(e) => setPassword(e.target.value)} />
            {mode === "signup" && <small className="text-3">At least 8 characters.</small>}
          </label>
          {err && <div className="auth-err" role="alert">{err}</div>}
          <button type="submit" className="composer-send auth-submit" disabled={busy}>{mode === "login" ? "Log in" : "Create account"}</button>
        </form>
        <div className="auth-or"><span>or</span></div>
        <button type="button" className="auth-demo" data-testid="demo-login" onClick={() => void go("demo")} disabled={busy}>
          Use the demo account
          <small>A shared workspace: anyone with the demo login sees its data.</small>
        </button>
      </div>
    </div>
  );
}
