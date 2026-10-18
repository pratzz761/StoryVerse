"use client";
import { useApp } from "./providers";
import { EmptyState, Loading } from "./ui";
import type { ReactNode } from "react";
export function AuthGate({ children }: { children: ReactNode }) {
  const { user, ready, openAuth, problem } = useApp();
  if (!ready) return <Loading/>;
  if (!user) return <EmptyState title="Every voice adds something." description={problem || "Sign in to create stories, save drafts, and write the next chapter."} action={<button className="button primary" onClick={openAuth}>Sign in to join in</button>}/>;
  return children;
}
