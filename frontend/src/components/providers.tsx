"use client";
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { LogIn, X } from "lucide-react";
import { errorMessage, request, supabase } from "@/lib/api";
import type { Health, Profile } from "@/lib/types";

type AppContext = { health: Health | null; user: Profile | null; ready: boolean; problem: string; openAuth: () => void; refresh: () => Promise<void>; toast: (message: string) => void };
const Context = createContext<AppContext | null>(null);
export const useApp = () => useContext(Context)!;

export function Providers({ children }: { children: ReactNode }) {
  const [health, setHealth] = useState<Health | null>(null);
  const [user, setUser] = useState<Profile | null>(null);
  const [ready, setReady] = useState(false);
  const [problem, setProblem] = useState("");
  const [auth, setAuth] = useState(false);
  const [notification, setNotification] = useState("");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const refresh = useCallback(async () => {
    try {
      const h = await request<Health>("/health");
      setHealth(h);
      setProblem("");
      const session = await supabase()?.auth.getSession();
      if (h.mode === "demo" || session?.data.session) setUser(await request<Profile>("/me"));
      else setUser(null);
      if (h.mode === "supabase" && !supabase()) setProblem("Add the public Supabase credentials to frontend/.env.local to enable sign in.");
    } catch (e) { setProblem(errorMessage(e)); }
    finally { setReady(true); }
  }, []);
  useEffect(() => {
    void refresh();
    const subscription = supabase()?.auth.onAuthStateChange(() => { setTimeout(() => void refresh(), 0); });
    return () => subscription?.data.subscription.unsubscribe();
  }, [refresh]);
  const toast = useCallback((message: string) => {
    if (timer.current) clearTimeout(timer.current);
    setNotification(message);
    timer.current = setTimeout(() => setNotification(""), 5000);
  }, []);
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);
  return <Context.Provider value={{ health, user, ready, problem, openAuth: () => setAuth(true), refresh, toast }}>
    {children}
    {notification && <div className="toast" role="status">{notification}<button aria-label="Dismiss notification" onClick={() => setNotification("")}><X size={16}/></button></div>}
    {auth && <AuthDialog close={() => setAuth(false)} />}
  </Context.Provider>;
}

function AuthDialog({ close }: { close: () => void }) {
  const [signup, setSignup] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const { refresh } = useApp();
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(""); setNotice("");
    const form = new FormData(event.currentTarget);
    try {
      const sb = supabase();
      if (!sb) throw new Error("Supabase credentials are missing. Follow the setup instructions to enable accounts.");
      const email = String(form.get("email")), password = String(form.get("password"));
      const result = signup ? await sb.auth.signUp({ email, password, options: { data: { display_name: String(form.get("name")) }, emailRedirectTo: `${window.location.origin}/profile` } }) : await sb.auth.signInWithPassword({ email, password });
      if (result.error) throw result.error;
      if (signup && !result.data.session) setNotice("Check your email to confirm your account, then sign in here.");
      else { await refresh(); close(); }
    } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }
  return <Modal title={signup ? "Your next chapter starts here" : "Welcome back"} close={close}>
    <p className="muted">{signup ? "Join a world of stories, made together." : "Sign in to write, contribute, and make it yours."}</p>
    <form onSubmit={submit} className="form-stack">
      {signup && <label>Display name<input name="name" autoComplete="name" required maxLength={50}/></label>}
      <label>Email<input name="email" type="email" autoComplete="email" required autoFocus/></label>
      <label>Password<input name="password" type="password" minLength={8} autoComplete={signup ? "new-password" : "current-password"} required/></label>
      {error && <p className="error" role="alert">{error}</p>}{notice && <p className="notice" role="status">{notice}</p>}
      <button className="button primary full" disabled={busy}><LogIn size={17}/>{busy ? "One moment…" : signup ? "Create account" : "Sign in"}</button>
    </form>
    <button className="text-button auth-switch" onClick={() => { setSignup(!signup); setError(""); setNotice(""); }}>{signup ? "Already have an account? Sign in" : "New around here? Create an account"}</button>
  </Modal>;
}

export function Modal({ title, close, children }: { title: string; close: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const oldOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const focusable = () => Array.from(ref.current?.querySelectorAll<HTMLElement>('button:not([disabled]),a[href],input:not([disabled]),textarea,select,[tabindex="0"]') || []);
    focusable()[0]?.focus();
    const key = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
      if (event.key === "Tab") {
        const nodes = focusable(); const first = nodes[0], last = nodes.at(-1);
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }
    };
    document.addEventListener("keydown", key);
    return () => { document.body.style.overflow = oldOverflow; document.removeEventListener("keydown", key); previous?.focus(); };
  }, [close]);
  return <div className="modal-backdrop" onMouseDown={e => { if (e.target === e.currentTarget) close(); }}>
    <div ref={ref} role="dialog" aria-modal="true" aria-labelledby="dialog-title" className="modal">
      <button className="icon-button modal-close" aria-label="Close dialog" onClick={close}><X size={20}/></button>
      <h2 id="dialog-title">{title}</h2>{children}
    </div>
  </div>;
}
