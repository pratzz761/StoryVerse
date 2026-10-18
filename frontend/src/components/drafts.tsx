"use client";
import Link from "next/link";
import { ArrowRight, FilePenLine, LockKeyhole } from "lucide-react";
import { useResource } from "@/lib/use-resource";
import { dateLabel } from "@/lib/api";
import type { Draft } from "@/lib/types";
import { EmptyState, ErrorState, Loading } from "./ui";
export function Drafts() {
  const { data, error, loading, reload } = useResource<Draft[]>("/drafts");
  return <div><div className="page-heading"><div><span className="eyebrow">ROOM TO THINK</span><h1>Some stories take their time.</h1><p>Your unpublished chapters, ready when you are.</p></div><span className="private-badge"><LockKeyhole size={14}/>Only visible to you</span></div>{loading ? <Loading/> : error ? <ErrorState message={error} retry={reload}/> : data?.length ? <div className="draft-list">{data.map(d => <Link href={`/studio/${d.id}`} key={d.id}><span className="draft-icon"><FilePenLine size={23}/></span><div><span className="eyebrow">{d.story_title}</span><h3>{d.title}</h3><p>{d.narrative.slice(0, 150) || "A chapter waiting for its words."}</p><small>Saved {dateLabel(d.created_at)} · Chapter {d.base_version + 1}</small></div><ArrowRight size={20}/></Link>)}</div> : <EmptyState title="A quiet corner for your ideas." description="Continue a story to create a private draft. You can come back and polish it before publishing." action={<Link href="/" className="button primary">Find a story<ArrowRight size={16}/></Link>}/>}</div>;
}
