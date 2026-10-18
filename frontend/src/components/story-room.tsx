"use client";
import Link from "next/link";
import { useState } from "react";
import { ArrowRight, BookOpen, Users, Rows3, PanelsTopLeft, PenLine, ChevronLeft, ChevronRight, Check } from "lucide-react";
import type { Story } from "@/lib/types";
import { useResource } from "@/lib/use-resource";
import { dateLabel } from "@/lib/api";
import { Avatar, BackLink, ErrorState, Loading, Media, EmptyState } from "./ui";
import { useApp } from "./providers";
import { ComicDescriptions } from "./comic-descriptions";
import { CommunityActions, PublishedBible } from "./community-actions";
import { useReading } from "@/lib/use-reading";
import { StoryReport } from "./story-report";

export function StoryRoom({ id }: { id: string }) {
  const { data: story, error, loading, reload } = useResource<Story>(`/stories/${id}`);
  const { user, openAuth } = useApp();
  const [layout, setLayout] = useState("webtoon");
  const [page, setPage] = useState(0);
  const reader = useReading(story, layout, (index, mode) => {setPage(index); setLayout(mode);});
  if (loading) return <Loading/>;
  if (error || !story) return <ErrorState message={error || "Story not found"} retry={reload}/>;
  const chapters = story.chapters || [];
  if (!chapters.length) return <EmptyState title="This story is waiting for its first chapter." description="Check back soon, or explore another world." action={<Link href="/" className="button secondary">Explore stories</Link>}/>;
  const authors = [...new Map(chapters.map(c => [c.author.id, c.author])).values()];
  const visible = layout === "comic" ? chapters.slice(page, page + 1) : chapters;
  return <div className="room-page"><BackLink href="/">Back to Explore</BackLink>
    <section className="room-header"><img className="room-cover" src={story.cover_url} alt={`Cover illustration for ${story.title}`}/><div className="room-info"><div className="room-tags"><span className="genre-tag static-tag">{story.genre}</span>{story.is_demo && <span className="subtle-badge">Hand-written demo story</span>}</div><h1>{story.title}</h1><p>{story.description}</p><div className="room-meta"><span><BookOpen size={15}/>{chapters.length} chapters</span><span><Users size={15}/>{story.contributor_count} contributors</span></div><div className="room-started"><Avatar person={story.owner} small/><span>Started by <strong>{story.owner.display_name}</strong></span></div></div><div className="room-action">{user ? <Link href={`/stories/${id}/continue`} className="button primary"><PenLine size={17}/>Continue story</Link> : <button className="button primary" onClick={openAuth}>Sign in to continue<ArrowRight size={16}/></button>}<small>The next chapter could be yours.</small></div></section>
    <CommunityActions id={id}/>
    <StoryReport storyId={id}/>
    <PublishedBible id={id}/>
    <div className="reader-grid"><div className="reader-main"><div className="reader-toolbar"><h2>The story so far <span>{chapters.length.toString().padStart(2, "0")}</span></h2><div className="segmented" aria-label="Reading layout"><button disabled={reader.busy} aria-pressed={layout === "webtoon"} className={layout === "webtoon" ? "selected" : ""} onClick={() => void reader.navigate(page, "webtoon")}><Rows3 size={15}/>Webtoon</button><button disabled={reader.busy} aria-pressed={layout === "comic"} className={layout === "comic" ? "selected" : ""} onClick={() => void reader.navigate(page, "comic")}><PanelsTopLeft size={15}/>Comic book</button></div></div>
      <section id="resume" className="reading-status" aria-label="Reading progress"><div><span>{reader.loading ? 'Loading reading progress…' : `Read through chapter ${reader.progress?.completed_position || 0} of ${chapters.length}`}</span>{reader.progress && <button className="text-button" disabled={reader.busy} onClick={reader.resume}>Continue reading<ArrowRight size={14}/></button>}</div><progress max={chapters.length} value={reader.progress?.completed_position || 0} aria-label="Chapters read"/>{!user && <small>Sign in to save your reading place across devices.</small>}{reader.error && <p className="error" role="alert">Your reading place could not be saved or loaded: {reader.error}</p>}</section>
      <div className={`chapter-reader ${layout}`}>
        {visible.map(c => <article className="chapter" tabIndex={-1} key={c.id} id={`chapter-${c.id}`}><div className="chapter-number"><span>{String(c.position).padStart(2, "0")}</span><div/></div><div className="chapter-content"><div className="chapter-kicker">CHAPTER {String(c.position).padStart(2, "0")}{c.source === "sample" ? <span>Sample content</span> : c.source === "demo_preview" ? <span>Contributor-written · demo preview</span> : c.source === "ai_generated" ? <span>{c.ai_metadata?.is_test_fixture ? "Mocked AI test fixture · contributor approved" : "AI-assisted · contributor approved"}</span> : <span>Contributor-written</span>}</div><h2>{c.title}</h2><div className="chapter-byline"><Avatar person={c.author} small/><strong>{c.author.display_name}</strong><span>·</span><time dateTime={c.created_at}>{dateLabel(c.created_at)}</time></div>
          {c.source === "sample" && <figure className="sample-panel"><img src={story.cover_url} alt={`Demo cover illustration for ${story.title}`} loading="lazy"/><figcaption>Sample cover artwork · Not a generated comic panel</figcaption></figure>}
          {c.panels.length > 0 && <div className="comic-panels">{c.attachments.filter(a => a.mime_type.startsWith("image/") && !c.comic_prompts?.some(p => p.image?.upload_id === a.id)).map(a => <figure key={a.id}><Media item={a}/><figcaption>Your uploaded image · {a.filename}</figcaption></figure>)}</div>}
          <div className="chapter-prose">{c.narrative.split(/\n\s*\n/).map((p, i) => <p key={i}>{p}</p>)}</div>
          {!!c.comic_prompts?.length && <ComicDescriptions panels={c.comic_prompts}/>}
          {c.attachments.filter(a => !a.mime_type.startsWith("image/")).map(a => <Media key={a.id} item={a}/>)}
          <button className="button secondary small mark-read" disabled={reader.busy} onClick={() => user ? void reader.navigate(c.position - 1, layout, true) : openAuth()}><Check size={14}/>{(reader.progress?.completed_position || 0) >= c.position ? `Chapter ${c.position} read` : `Mark chapter ${c.position} read`}</button>
        </div></article>)}
      </div>
      <nav className="reader-pagination" aria-label="Chapter navigation"><button className="button secondary small" disabled={reader.busy || page === 0} onClick={() => void reader.navigate(page - 1)}><ChevronLeft size={16}/>Previous</button><span>Chapter {page + 1} of {chapters.length}</span><button className="button secondary small" disabled={reader.busy || page >= chapters.length - 1} onClick={() => void reader.navigate(page + 1)}>Next<ChevronRight size={16}/></button></nav>
      <div className="continue-card"><span className="aside-symbol"><PenLine size={22}/></span><h2>And then…?</h2><p>Every new voice takes the story somewhere unexpected.</p><Link href={`/stories/${id}/continue`} className="button primary">Write the next chapter<ArrowRight size={17}/></Link></div>
    </div><aside className="room-rail"><div className="rail-block"><div className="rail-heading"><h3>Made together</h3><Users size={16}/></div><p className="muted small-text">The voices behind this world.</p>{authors.map(a => <div className="contributor" key={a.id}><Avatar person={a}/><div><strong>{a.display_name}</strong><small>{chapters.filter(c => c.author.id === a.id).length} {chapters.filter(c => c.author.id === a.id).length === 1 ? "chapter" : "chapters"}</small></div>{a.id === story.owner_id && <span className="creator-label">Creator</span>}</div>)}</div><div className="rail-block chapter-index"><h3>In this story</h3>{chapters.map((c, i) => <button key={c.id} onClick={() => { void reader.navigate(i); }}><span>{String(c.position).padStart(2, "0")}</span>{c.title}<Check size={13}/></button>)}</div><div className="rail-note"><BookOpen size={20}/><p>A shared world, one chapter at a time. Your contribution stays private until you approve and publish it.</p></div></aside></div>
  </div>;
}
