"use client";
import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";
import { ArrowRight, BookOpen, Users, AlertCircle, RefreshCw, Feather, LoaderCircle, Heart } from "lucide-react";
import type { Attachment, Profile, Story } from "@/lib/types";
import { privateMedia } from "@/lib/api";

export function Avatar({ person, small = false }: { person: Pick<Profile, "display_name" | "avatar_color">; small?: boolean }) {
  return <span className={`avatar ${person.avatar_color || "purple"} ${small ? "avatar-small" : ""}`} aria-hidden="true">{person.display_name.split(" ").slice(0, 2).map(x => x[0]).join("")}</span>;
}
export function StoryCard({ story }: { story: Story }) {
  return <article className="story-card">
    <Link href={`/stories/${story.id}`} className="story-cover-link" tabIndex={-1} aria-hidden="true"><img className="story-cover" src={story.cover_url} alt="" loading="lazy"/><span className={`genre-tag genre-${story.genre.toLowerCase().replaceAll(" ", "-")}`}>{story.genre}</span>{story.is_demo && <span className="sample-tag">Demo story</span>}</Link>
    <div className="story-card-body"><Link href={`/stories/${story.id}`} className="story-title"><h3>{story.title}</h3><ArrowRight size={17}/></Link><p className="card-description">{story.description}</p><div className="story-card-meta"><span><Users size={14}/>{story.contributor_count} {story.contributor_count === 1 ? "contributor" : "contributors"}</span><span><BookOpen size={14}/>{story.chapter_count} {story.chapter_count === 1 ? "chapter" : "chapters"}</span></div></div>
    <div className="card-community"><span><Heart size={13}/>{story.like_count ?? 0} likes</span>{story.reading_progress && <Link href={`/stories/${story.id}#resume`}>Continue reading · Chapter {Math.min(story.chapter_count, Math.max(story.reading_progress.position, story.reading_progress.completed_position + 1))}<ArrowRight size={13}/></Link>}</div>
  </article>;
}
export function Loading({ label = "Opening the next chapter…" }: { label?: string }) {
  return <div className="state-box" role="status"><LoaderCircle size={25} className="spinner"/><p>{label}</p></div>;
}
export function ErrorState({ message, retry }: { message: string; retry?: () => void }) {
  return <div className="state-box"><AlertCircle size={28}/><h2>We lost the thread</h2><p role="alert">{message}</p>{retry && <button onClick={retry} className="button secondary"><RefreshCw size={16}/>Try again</button>}</div>;
}
export function EmptyState({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return <div className="state-box empty-state"><Feather size={30}/><h2>{title}</h2><p>{description}</p>{action}</div>;
}
export function BackLink({ href, children }: { href: string; children: ReactNode }) {
  return <Link href={href} className="back-link"><ArrowRight size={15} style={{ transform: "rotate(180deg)" }}/>{children}</Link>;
}
export function DemoNotice({ studio = false }: { studio?: boolean }) {
  return <div className="demo-notice"><span className="notice-icon"><Feather size={16}/></span><div><strong>{studio ? "Demo preview · Your words, unchanged" : "A little transparency"}</strong><p>{studio ? "This preview copies your contribution as written. No AI was used. Edit it manually, or choose Generate with AI when a text provider is configured. Nothing is published without your approval." : "These are hand-written sample stories. Real AI text generation is available when configured; demo previews are always labeled."}</p></div></div>;
}
export function Media({ item, privateFile = false }: { item: Attachment; privateFile?: boolean }) {
  const [url, setUrl] = useState(privateFile ? "" : item.url);
  const [error, setError] = useState(false);
  useEffect(() => {
    if (!privateFile) return;
    let active = true; let objectUrl = "";
    privateMedia(item.url).then(value => { objectUrl = value; if (active) setUrl(value); else URL.revokeObjectURL(value); }).catch(() => { if (active) setError(true); });
    return () => { active = false; if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [item.url, privateFile]);
  if (error) return <p className="error">Couldn&apos;t load {item.filename}.</p>;
  if (!url) return <div className="media-loading">Loading attachment…</div>;
  if (item.mime_type.startsWith("image/")) return <img className="media-image" src={url} alt={item.filename} loading="lazy"/>;
  if (item.mime_type.startsWith("audio/")) return <div className="audio-attachment"><span>{item.filename}</span><audio controls preload="metadata" src={url}/></div>;
  return <video className="media-video" controls preload="metadata" src={url} aria-label={item.filename}/>;
}
