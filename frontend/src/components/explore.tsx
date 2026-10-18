"use client";
import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import { useEffect, useRef } from "react";
import { ArrowRight, Plus, TrendingUp, Clock3, Users, BookOpen, X, Feather } from "lucide-react";
import { GENRES, type Discovery } from "@/lib/types";
import { useResource } from "@/lib/use-resource";
import { useApp } from "./providers";
import { Avatar, DemoNotice, EmptyState, ErrorState, Loading, StoryCard } from "./ui";

export function Explore() {
  const params = useSearchParams();
  const router = useRouter();
  const q = params.get("q") || "";
  const sort = params.get("sort") === "recent" ? "recent" : "trending";
  const genre = params.get("genre") || "";
  const page = Math.max(1, Number(params.get("page")) || 1);
  const pendingParams = useRef(params.toString());
  useEffect(() => {pendingParams.current = params.toString();}, [params]);
  function filter(key: string, value: string) {
    const next = new URLSearchParams(pendingParams.current);
    next.set(key, value);
    if (key !== "page") next.delete("page");
    pendingParams.current = next.toString();
    router.push(`/?${next}`, {scroll:false});
  }
  const setSort = (value: string) => filter("sort", value);
  const setGenre = (value: string) => filter("genre", value);
  const { health } = useApp();
  const query = new URLSearchParams({ sort, search: q, page:String(page), page_size:"12", ...(genre ? { genre } : {}) });
  const { data, loading, error, reload } = useResource<Discovery>(`/discover?${query}`);
  const stories = data?.items;
  const featured = stories?.[0];
  return <div className="explore-page">
    <div className="page-heading"><div><div className="eyebrow"><span className="purple-line"/>A WORLD BUILT TOGETHER</div><h1>Good stories don&apos;t end here.</h1><p>Find a world you love. Help write what happens next.</p></div><Link href="/create" className="button primary"><Plus size={18}/>Create story</Link></div>
    {!q && !genre && page === 1 && featured && !loading && <section className={`featured featured-${featured.cover_art}`} aria-label="Featured story">
      <img src={featured.cover_url} alt="An illustrated world waiting to be explored" className="featured-art"/>
      <div className="featured-shade"/>
      <div className="featured-content"><div className="featured-label"><span/>THE STORY SPOTLIGHT{featured.is_demo && <span className="featured-demo">DEMO</span>}</div><span className="featured-genre">{featured.genre} <span>·</span> An unfolding adventure</span><h2>{featured.title}</h2><p>{featured.description}</p><Link className="button cream" href={`/stories/${featured.id}`}>Step into the story<ArrowRight size={17}/></Link><div className="featured-credit"><Avatar person={featured.owner} small/><span>Started by <strong>{featured.owner.display_name}</strong></span><span className="credit-divider"/><span><BookOpen size={13}/>{featured.chapter_count} chapters so far</span></div></div>
      <span className="art-caption">A WORLD WAITING FOR YOUR NEXT CHAPTER</span>
    </section>}
    <section className="feed-section" aria-label="Story feed">
      <div className="feed-toolbar"><div className="feed-tabs" role="tablist" aria-label="Story order"><button role="tab" aria-selected={sort === "trending"} className={sort === "trending" ? "selected" : ""} onClick={() => setSort("trending")}><TrendingUp size={17}/>Trending</button><button role="tab" aria-selected={sort === "recent"} className={sort === "recent" ? "selected" : ""} onClick={() => setSort("recent")}><Clock3 size={16}/>Recent</button></div><span className="feed-caption"><Users size={15}/>A different perspective on every page</span></div>
      <div className="genre-filters" aria-label="Filter by genre">{["All genres", ...GENRES].map((g, i) => <button key={g} aria-pressed={i === 0 ? genre === "" : genre === g} onClick={() => setGenre(i === 0 ? "" : g)} className={(i === 0 ? !genre : genre === g) ? "selected" : ""}>{g}</button>)}</div>
      {q && <div className="search-results">Stories matching <strong>“{q}”</strong><button className="text-button" onClick={() => router.push("/")}><X size={14}/>Clear search</button></div>}
      {loading ? <div className="skeleton-grid" aria-label="Loading stories">{[0,1,2].map(n => <div key={n} className="skeleton-card"><div/><span/><span/></div>)}</div> : error ? <ErrorState message={error} retry={reload}/> : stories?.length ? <div className="story-grid">{stories.map(story => <StoryCard key={story.id} story={story}/>)}</div> : <EmptyState title={q || genre ? "No stories in this corner. Yet." : "An empty page. Endless possibilities."} description={q || genre ? "Try a different search or genre, or start a story of your own." : "Be the first to start a world worth sharing."} action={<Link href="/create" className="button secondary"><Plus size={16}/>Start a story</Link>}/>}
    </section>
    {data && !loading && !error && data.total > 0 && <nav className="reader-pagination discovery-pagination" aria-label="Story pages"><button className="button secondary small" disabled={page <= 1} onClick={() => filter("page", String(page - 1))}>Previous stories</button><span>Page {page} of {Math.max(1, Math.ceil(data.total / data.page_size))} · {data.total} stories</span><button className="button secondary small" disabled={!data.has_next} onClick={() => filter("page", String(page + 1))}>Next stories</button></nav>}
    {health?.mode === "demo" && <DemoNotice/>}
    <div className="community-strip"><div className="community-icon"><Feather size={21}/></div><div><strong>One story. Many imaginations.</strong><p>You don&apos;t need to know the ending to be part of the story.</p></div><Link href="/create">Make a beginning<ArrowRight size={16}/></Link></div>
  </div>;
}
