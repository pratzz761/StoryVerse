"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, BookOpen, LockKeyhole, Waypoints, Globe2, UserRoundPlus, CornerUpRight, Sparkles, LoaderCircle } from "lucide-react";
import { DIRECTIONS, type Story, type Attachment } from "@/lib/types";
import { useResource } from "@/lib/use-resource";
import { post, errorMessage } from "@/lib/api";
import { BackLink, DemoNotice, ErrorState, Loading } from "./ui";
import { Uploads } from "./uploads";
import { useApp } from "./providers";
import { textProviderName, textProviderDisclosure } from "@/lib/text-provider";

export function ContinueStory({ id }: { id: string }) {
  const { data: story, loading, error, reload } = useResource<Story>(`/stories/${id}`);
  const router = useRouter();
  const { health, toast } = useApp();
  const providerName = textProviderName(health);
  const [consent, setConsent] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [text, setText] = useState("");
  const [direction, setDirection] = useState<string>(DIRECTIONS[0]);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [uploading, setUploading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");
  const directionIcons = [CornerUpRight, Waypoints, Globe2, UserRoundPlus];
  async function submit(event: React.FormEvent) {
    event.preventDefault(); if (!story || busy || uploading) return;
    const useAI = ((event.nativeEvent as SubmitEvent).submitter as HTMLButtonElement | null)?.value === "ai";
    if (useAI && !consent) { setProblem(`Confirm that you want to send your idea and the necessary story context to ${providerName} first.`); return; }
    setBusy(true); setProblem("");
    try {
      const draft = await post<{id: string}>(`/stories/${id}/contributions`, { text, direction, expected_version: story.version, upload_ids: attachments.map(a => a.id) });
      if (useAI) {
        setGenerating(true);
        try {
          const result = await post<{id: string}>(`/drafts/${draft.id}/generate`, { request_id: crypto.randomUUID(), expected_revision: 0, consent: true });
          router.push(`/studio/${result.id}`); return;
        } catch (e) { toast(`${errorMessage(e)} Your original contribution is saved in the studio.`); }
      }
      router.push(`/studio/${draft.id}`);
    } catch (e) { setProblem(errorMessage(e)); setBusy(false); setGenerating(false); }
  }
  if (loading) return <Loading/>;
  if (error || !story) return <ErrorState message={error || "Story not found"} retry={reload}/>;
  const last = story.chapters?.at(-1);
  return <div className="writing-page"><BackLink href={`/stories/${id}`}>Back to {story.title}</BackLink><div className="page-heading"><div><span className="eyebrow">CHAPTER {String(story.version + 1).padStart(2, "0")} · YOUR TURN</span><h1>Where do we go from here?</h1><p>A new perspective. A small surprise. A whole new direction.</p></div></div>
    <div className="writing-grid"><form onSubmit={submit} className="editor-card form-stack">
      {last && <section className="previous-chapter"><div><BookOpen size={16}/><strong>Previous chapter summary</strong><span>{last.summary?.source === "ai" ? "AI chapter summary" : "Verbatim excerpt · no AI"}</span></div><h3>{last.title}</h3><p>{last.summary?.source === "ai" ? last.summary.synopsis : `${last.narrative.slice(0, 650)}${last.narrative.length > 650 ? "…" : ""}`}</p></section>}
      <label>Your contribution<span className="field-hint">Tell us what happens next. This stays private until you publish.</span><textarea autoFocus value={text} onChange={e => setText(e.target.value)} maxLength={12000} rows={10} placeholder="What if, just as they turned to leave…"/><span className="character-count">{text.length.toLocaleString()} / 12,000</span></label>
      <div><span className="field-label">Add your inspiration <span className="optional">Optional</span></span><Uploads value={attachments} onChange={setAttachments} onBusy={setUploading}/></div>
      <fieldset className="direction-fieldset"><legend>Creative direction</legend><p className="field-hint">Guides {providerName} when you generate with AI. Demo previews keep your words unchanged.</p><div className="direction-options">{DIRECTIONS.map((d, i) => { const Icon = directionIcons[i]; return <label key={d} className={direction === d ? "selected" : ""}><input type="radio" name="direction" value={d} checked={direction === d} onChange={() => setDirection(d)}/><Icon size={18}/>{d}</label>; })}</div></fieldset>
      {health?.ai_enabled ? <label className="checkbox-label ai-consent"><input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)}/><span>Send my idea and necessary published story context to {providerName}. {textProviderDisclosure(health)}</span></label> : <p className="field-hint">The text provider isn&apos;t configured. The explicitly labeled demo preview is available below.</p>}
      {generating && <div className="generation-progress" role="status"><LoaderCircle size={19} className="spinner"/><div><strong>{health?.ai?.mocked ? "Preparing the mocked test response…" : `Building context and waiting for ${providerName}…`}</strong><p>Your idea is saved. You&apos;ll review the result before anything is published.</p></div></div>}
      {problem && <div className="error" role="alert">{problem}<br/><a href={`/stories/${id}`}>Read the latest story</a>. Your text is still here; copy it before leaving.</div>}
      <div className="form-actions generation-actions"><span><LockKeyhole size={15}/>Private until you approve</span><div><button className={`button ${health?.ai_enabled ? "secondary" : "primary"}`} name="mode" value="demo" disabled={busy || uploading || (!text.trim() && !attachments.length)}>{busy && !generating ? "Preparing preview…" : "Generate preview"}<ArrowRight size={17}/></button>{health?.ai_enabled && <button className="button primary" name="mode" value="ai" disabled={busy || uploading || !text.trim() || !consent}><Sparkles size={16}/>{generating ? "Generating…" : "Generate with AI"}</button>}</div></div>
    </form><aside className="writing-aside"><span className="aside-symbol"><Waypoints size={24}/></span><h3>Your voice belongs here.</h3><p>Build on the chapter before yours, then give the next storyteller something to work with.</p><ol className="flow-steps"><li className="current"><span>1</span><div><strong>Add your contribution</strong><small>Words, images, audio, video</small></div></li><li><span>2</span><div><strong>Make it your own</strong><small>Review and edit in Chapter Studio</small></div></li><li><span>3</span><div><strong>Let the story continue</strong><small>Approve and publish your chapter</small></div></li></ol><DemoNotice studio/></aside></div>
  </div>;
}
