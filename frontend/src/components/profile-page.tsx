"use client";
import Link from "next/link";
import { useCallback, useState } from "react";
import { BookOpen, CalendarDays, Pencil, Plus, Users } from "lucide-react";
import { patch, errorMessage, dateLabel } from "@/lib/api";
import { useResource } from "@/lib/use-resource";
import type { Library } from "@/lib/types";
import { Modal, useApp } from "./providers";
import { Avatar, EmptyState, ErrorState, Loading, StoryCard } from "./ui";

export function ProfilePage() {
  const { user, health, refresh, toast } = useApp();
  const { data, loading, error, reload } = useResource<Library>("/me/stories");
  const [tab, setTab] = useState<keyof Library>("created");
  const [edit, setEdit] = useState(false);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");
  const close = useCallback(() => setEdit(false), []);
  const empty = {
    created: ["Your first story is waiting.", "A single sentence can open a whole new world."],
    contributed: ["Someone else's world could use your voice.", "Find a story that sparks something, then write the next chapter."],
    bookmarked: ["Keep a few stories for later.", "Bookmark a story from its reading room to find it here."],
    followed: ["Find a world to follow.", "Follow a story to keep its latest chapters in your library."],
    reading: ["Pick up a story.", "Use chapter navigation or mark a chapter read to save your reading place."]
  };
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setProblem("");
    const form = new FormData(event.currentTarget);
    try { await patch("/me", { display_name: form.get("name"), bio: form.get("bio") }); await refresh(); setEdit(false); toast("Profile updated."); }
    catch (e) { setProblem(errorMessage(e)); } finally { setBusy(false); }
  }
  if (!user) return null;
  return <div className="profile-page"><div className="profile-cover"><div className="profile-cover-lines"/><span>A STORY IS BETTER WITH YOU IN IT.</span></div><section className="profile-info"><div className="profile-avatar"><Avatar person={user}/></div><div className="profile-identity"><div className="profile-name"><h1>{user.display_name}</h1>{health?.mode === "demo" && <span className="subtle-badge">Demo profile</span>}</div><p>{user.bio || "A new voice. A thousand possible stories."}</p><div className="profile-stats"><span><CalendarDays size={14}/>Joined {dateLabel(user.created_at)}</span><span><BookOpen size={14}/>{data?.created.length ?? "—"} stories created</span><span><Users size={14}/>{data?.contributed.length ?? "—"} stories contributed</span></div></div><button className="button secondary small" onClick={() => setEdit(true)}><Pencil size={15}/>Edit profile</button></section>
    <div className="profile-feed-heading"><div className="feed-tabs library-tabs" role="tablist" aria-label="Your stories">{([['created','Created stories'],['contributed','Contributed stories'],['bookmarked','Bookmarked'],['followed','Followed'],['reading','Continue reading']] as const).map(([key,label]) => <button key={key} role="tab" aria-selected={tab === key} className={tab === key ? 'selected' : ''} onClick={() => setTab(key)}>{label} <span>{data?.[key].length || 0}</span></button>)}</div><Link href="/create" className="button primary small"><Plus size={16}/>Create story</Link></div>
    {loading ? <Loading/> : error ? <ErrorState message={error} retry={reload}/> : data?.[tab].length ? <div className="story-grid">{data[tab].map(s => <StoryCard key={s.id} story={s}/>)}</div> : <EmptyState title={empty[tab][0]} description={empty[tab][1]} action={<Link href={tab === "created" ? "/create" : "/"} className="button primary">{tab === "created" ? "Start a story" : "Explore stories"}</Link>}/>}
    {edit && <Modal title="A little about you" close={close}><form onSubmit={submit} className="form-stack"><label>Display name<input name="name" defaultValue={user.display_name} maxLength={50} required/></label><label>Bio<textarea name="bio" defaultValue={user.bio} rows={4} maxLength={300} placeholder="What worlds do you like to wander?"/></label>{problem && <p className="error" role="alert">{problem}</p>}<div className="modal-actions"><button type="button" className="button secondary" onClick={close}>Cancel</button><button className="button primary" disabled={busy}>{busy ? "Saving…" : "Save profile"}</button></div></form></Modal>}
  </div>;
}
