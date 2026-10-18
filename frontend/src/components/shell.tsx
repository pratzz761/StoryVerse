"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Compass, BookOpen, FilePenLine, Plus, Search, ArrowUpRight, LogOut, ChevronDown, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { useState, type ReactNode } from "react";
import { useApp } from "./providers";
import { Avatar } from "./ui";
import { supabase } from "@/lib/api";

export function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, health, problem, openAuth, refresh } = useApp();
  const [search, setSearch] = useState("");
  const [compact, setCompact] = useState(false);
  const nav = [{ href: "/", label: "Explore", icon: Compass }, { href: "/profile", label: "My stories", icon: BookOpen }, { href: "/drafts", label: "Drafts", icon: FilePenLine }];
  const section = pathname === "/" ? "Explore" : pathname.startsWith("/profile") ? "My profile" : pathname.startsWith("/drafts") ? "Drafts" : pathname.startsWith("/create") ? "Create a story" : pathname.startsWith("/studio") ? "Chapter Studio" : "Story room";
  return <div className={`app ${compact ? "compact-sidebar" : ""}`}>
    <a href="#main-content" className="skip-link">Skip to content</a>
    <aside className="sidebar">
      <Link className="brand" href="/" aria-label="StoryVerse home"><BrandMark/><span>Story<span className="brand-light">Verse</span><span className="brand-dot">.</span></span></Link>
      <div className="nav-label">YOUR NEXT CHAPTER</div>
      <nav aria-label="Main navigation">{nav.map(({ href, label, icon: Icon }) => <Link key={href} href={href} aria-label={label} aria-current={pathname === href ? "page" : undefined} className={`nav-link ${pathname === href ? "active" : ""}`}><Icon size={20}/><span>{label}</span>{pathname === href && <span className="active-dot"/>}</Link>)}</nav>
      <Link href="/create" aria-label="Create story" className="button primary sidebar-create"><Plus size={18}/><span>Create story</span></Link>
      <div className="sidebar-bottom">
        <div className="sidebar-note"><span className="tiny-star">✳</span><p>Good stories have<br/>more than one voice.</p><Link href="/create">Add yours <ArrowUpRight size={14}/></Link></div>
        {health?.mode === "demo" && <div className="workspace-label"><span/>Local demo workspace</div>}
        {user ? <div className="sidebar-user"><Link href="/profile" className="user-link"><Avatar person={user}/><span><strong>{user.display_name}</strong><small>{health?.mode === "demo" ? "Demo profile" : "Storyteller"}</small></span></Link>{health?.mode === "supabase" && <button className="icon-button" aria-label="Sign out" onClick={async () => { await supabase()?.auth.signOut(); await refresh(); router.push("/"); }}><LogOut size={16}/></button>}</div> : <button className="button secondary full" onClick={openAuth}>Sign in</button>}
      </div>
    </aside>
    <div className="main-shell">
      <header className="topbar">
        <div className="topbar-section"><button className="icon-button collapse-button" aria-label={compact ? "Expand sidebar" : "Collapse sidebar"} onClick={() => setCompact(!compact)}>{compact ? <PanelLeftOpen size={19}/> : <PanelLeftClose size={19}/>}</button><span className="desktop-section">{section}</span><Link className="mobile-brand brand" href="/"><BrandMark/><span>StoryVerse<span className="brand-dot">.</span></span></Link></div>
        <form className="global-search" role="search" onSubmit={e => { e.preventDefault(); router.push(`/?q=${encodeURIComponent(search.trim())}`); }}><Search size={17}/><input aria-label="Search stories" placeholder="Find your next story…" value={search} maxLength={100} onChange={e => setSearch(e.target.value)}/><kbd>↵</kbd></form>
        <div className="topbar-account">{user ? <Link href="/profile" aria-label="Your profile"><Avatar person={user} small/><ChevronDown size={13}/></Link> : <button className="button secondary small" onClick={openAuth}>Sign in</button>}</div>
      </header>
      {problem && <div className="connection-banner" role="alert">{problem} <button className="text-button" onClick={() => void refresh()}>Retry connection</button></div>}
      <main id="main-content" className="main-content">{children}</main>
      <footer className="page-footer"><span>StoryVerse<span className="brand-dot">.</span> A little imagination. A world of possibilities.</span><span>Made to be continued.</span></footer>
    </div>
    <nav className="mobile-nav" aria-label="Mobile navigation">{nav.map(({ href, label, icon: Icon }) => <Link key={href} className={pathname === href ? "active" : ""} href={href}><Icon size={20}/><span>{label}</span></Link>)}<Link className={pathname === "/create" ? "active" : ""} href="/create"><Plus size={20}/><span>Create</span></Link></nav>
  </div>;
}

export function BrandMark() { return <svg viewBox="0 0 28 30" width="28" height="30" fill="none" aria-hidden="true"><path d="m3 3 10 4v20L3 23V3Z" fill="#8B5CF6"/><path d="m15 7 10-4v20l-10 4V7Z" fill="#B69AF9"/><path d="m8 0 6 3 6-3v4l-6 3-6-3V0Z" fill="#F5EBDD"/></svg>; }
