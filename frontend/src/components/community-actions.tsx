"use client";
import { useEffect, useState } from "react";
import { Heart, Bookmark, Bell } from "lucide-react";
import type { Engagement, StoryBible } from "@/lib/types";
import { useResource } from "@/lib/use-resource";
import { post, errorMessage } from "@/lib/api";
import { useApp } from "./providers";

export function CommunityActions({ id }: {id: string}) {
  const resource = useResource<Engagement>(`/stories/${id}/engagement`);
  const [value, setValue] = useState<Engagement | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const {user, openAuth} = useApp();
  useEffect(() => {setValue(resource.data);}, [resource.data]);
  async function change(kind: "like" | "bookmark" | "follow") {
    if (!user) {openAuth(); return;}
    if (busy || !value) return;
    setBusy(true); setError("");
    try {setValue(await post<Engagement>(`/stories/${id}/interactions`, {kind, active: !value[kind]}));}
    catch (e) {setError(errorMessage(e));} finally {setBusy(false);}
  }
  return <section className="community-actions" aria-label="Story community">
    <div>{([['like', Heart, 'Like', 'Liked'], ['bookmark', Bookmark, 'Bookmark', 'Bookmarked'], ['follow', Bell, 'Follow story', 'Following story']] as const).map(([kind, Icon, label, activeLabel]) =>
      <button key={kind} className={`button secondary small ${value?.[kind] ? 'community-selected' : ''}`} aria-pressed={value?.[kind] || false} disabled={busy || !value} onClick={() => void change(kind)}>
        <Icon size={16}/>{value?.[kind] ? activeLabel : label}<span aria-label={`${kind} count`}>{value?.[`${kind}_count`] ?? '—'}</span>
      </button>)}</div>
    {resource.loading && <small role="status">Loading community…</small>}
    {(error || resource.error) && <p className="error" role="alert">{error || resource.error} <button className="text-button" onClick={resource.reload}>Refresh community</button></p>}
  </section>;
}

export function PublishedBible({ id }: {id: string}) {
  const {data, loading, error, reload} = useResource<StoryBible>(`/stories/${id}/bible`);
  return <details className="chapter-notes story-bible"><summary>Story Bible · Characters & continuity</summary>
    <p>Published story facts. Draft changes join this record only after approval.</p>
    {loading ? <p role="status">Loading story facts…</p> : error ? <p className="error" role="alert">{error} <button className="text-button" onClick={reload}>Try again</button></p> : <>
      {!data?.data.characters.length && <p>No character facts recorded yet. AI chapters add continuity notes when published.</p>}
      {data?.data.characters.map(c => <section key={c.name} className="bible-character"><h4>{c.name}</h4><p>{c.description}</p>{c.visual_description && <p><strong>Appearance:</strong> {c.visual_description}</p>}{c.personality_traits.length > 0 && <p><strong>Personality:</strong> {c.personality_traits.join(', ')}</p>}{c.relationships.length > 0 && <p><strong>Relationships:</strong> {c.relationships.join(' ')}</p>}</section>)}
      {!!data?.data.important_events.length && <><h4>Important events</h4><ul>{data.data.important_events.map(e => <li key={e}>{e}</li>)}</ul></>}
    </>}
  </details>;
}
