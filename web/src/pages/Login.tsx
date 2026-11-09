import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { ApiError } from "../api/client";
import { Avatar } from "../components/Avatar";
import { DEFAULT_LENSBOT_SHAPE } from "../components/robot/look";
import { BOT_DEFAULT_COLORS } from "../components/robot/palette";
import type { AvatarOut } from "../api/types";

// The ghost that sits on the login card's top edge.
const MASCOT: AvatarOut = { shape: DEFAULT_LENSBOT_SHAPE, color: BOT_DEFAULT_COLORS[0], badge: "none" };

type Mode = "login" | "register";

export function Login() {
  const { login, register } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState<Mode>("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      if (mode === "login") {
        await login(username, password);
      } else {
        await register(username, password);
      }
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't reach Roost. Check that it's running, then try again.");
    } finally {
      setSubmitting(false);
    }
  };

  const isLogin = mode === "login";

  return (
    <div className="login-page">
      <form className="login-card" onSubmit={(event) => void onSubmit(event)}>
        <div className="login-card__bird" aria-hidden="true">
          <Avatar avatar={MASCOT} status="resting" size={88} label={false} decorative />
        </div>
        <h1 className="login-card__title">Roost</h1>
        <p className="login-card__lede">
          {isLogin ? "Log in to talk to your team." : "Create the one account for this Roost."}
        </p>
        <label className="field">
          <span className="field__label">Username</span>
          <input
            className="input"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            autoComplete="username"
            autoCapitalize="off"
            spellCheck={false}
            required
          />
        </label>
        <label className="field">
          <span className="field__label">Password</span>
          <input
            className="input"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete={isLogin ? "current-password" : "new-password"}
            required
          />
        </label>
        {error ? (
          <p className="form-error" role="alert">
            {error}
          </p>
        ) : null}
        <button type="submit" className="btn btn--primary btn--block" disabled={submitting}>
          {isLogin ? "Log in" : "Create account"}
        </button>
        <button
          type="button"
          className="btn-text login-card__switch"
          onClick={() => {
            setError(null);
            setMode((prev) => (prev === "login" ? "register" : "login"));
          }}
        >
          {isLogin ? "First time? Create your account" : "Already have an account? Log in"}
        </button>
      </form>
    </div>
  );
}
