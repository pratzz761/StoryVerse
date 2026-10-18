"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Check, ImageIcon, LockKeyhole, RefreshCw, Save, BookOpen, Eye, PenLine, Sparkles, LoaderCircle } from "lucide-react";
import { useResource } from "@/lib/use-resource";
import { errorMessage, patch, post, request, waitImageJob, type ImageJob } from "@/lib/api";
import type { Draft } from "@/lib/types";
import { BackLink, DemoNotice, ErrorState, Loading, Media } from "./ui";
import { Modal, useApp } from "./providers";
import { AINotice, ComicDescriptions } from "./comic-descriptions";
import { textProviderName, textProviderDisclosure } from "@/lib/text-provider";

export function Studio({ id }: { id: string }) {
  const { data: draft, loading, error, reload } = useResource<Draft>(`/drafts/${id}`);
  const [title, setTitle] = useState("");
  const [narrative, setNarrative] = useState("");
  const [busy, setBusy] = useState("");
  const [problem, setProblem] = useState("");
  const [confirm, setConfirm] = useState<"publish" | "regenerate" | "ai" | "image" | null>(null);
  const [panelIndex, setPanelIndex] = useState<number | null>(null);
  const [view, setView] = useState("edit");
  const [saved, setSaved] = useState(true);
  const { toast, health } = useApp();
  const providerName = textProviderName(health);
  const router = useRouter();
  const close = useCallback(() => setConfirm(null), []);
  useEffect(() => { if (draft) { setTitle(draft.title); setNarrative(draft.narrative); setSaved(true); } }, [draft]);
  useEffect(() => {
    if (!draft?.pending_image_job) return;
    const controller = new AbortController();
    setBusy("image");
    waitImageJob({job_id:draft.pending_image_job}, controller.signal).then(result => {
      if (!controller.signal.aborted) router.push(`/studio/${result.id}`);
    }).catch(error => { if (!controller.signal.aborted) setProblem(errorMessage(error)); })
      .finally(() => { if (!controller.signal.aborted) setBusy(""); });
    return () => controller.abort();
  }, [draft?.pending_image_job, router]);
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => { if (!saved) { e.preventDefault(); } };
    window.addEventListener("beforeunload", handler); return () => window.removeEventListener("beforeunload", handler);
  }, [saved]);
  async function save() {
    await patch(`/drafts/${id}`, { title, narrative }); setSaved(true);
  }
  async function action(kind: string) {
    if (busy || !draft) return;
    setBusy(kind); setProblem("");
    try {
      if (kind === "save") { await save(); toast("Draft saved. Take your time."); }
      if (kind === "publish") {
        await save();
        const result = await post<{story_id: string}>(`/drafts/${id}/publish`, { expected_version: draft.base_version, approved: true });
        close(); toast("Your chapter is published. The story continues."); router.push(`/stories/${result.story_id}`);
      }
      if (kind === "regenerate") {
        const reset = await post<Draft>(`/drafts/${id}/regenerate`, {});
        setTitle(reset.title); setNarrative(reset.narrative); setSaved(true); close(); toast("Demo preview reset to your original contribution. No AI was used.");
      }
      if (kind === "ai") {
        await save();
        const current = await request<Draft>(`/drafts/${id}`);
        const path = panelIndex === null ? `/drafts/${id}/generate` : `/drafts/${id}/panels/${panelIndex}/regenerate`;
        const result = await post<{id: string}>(path, { request_id: crypto.randomUUID(), expected_revision: current.revision ?? 0, consent: true });
        close(); toast("A new version is ready. Your previous saved draft is still available.");
        router.push(`/studio/${result.id}`);
      }
      if (kind === "image" && panelIndex !== null) {
        await save();
        const current = await request<Draft>(`/drafts/${id}`);
        const queued = await post<ImageJob>(`/drafts/${id}/panels/${panelIndex}/image`, { request_id:crypto.randomUUID(), expected_revision:current.revision ?? 0, consent:true });
        const result = await waitImageJob(queued);
        close(); toast("A new panel version is ready. Your previous draft is preserved.");
        router.push(`/studio/${result.id}`);
      }
    } catch (e) { setProblem(errorMessage(e)); close(); } finally { setBusy(""); }
  }
  if (loading) return <Loading label="Opening your private studio…"/>;
  if (error || !draft) return <ErrorState message={error || "Draft not found"} retry={reload}/>;
  if (draft.status === "published") return <div className="state-box"><Check size={30}/><h1>This chapter is out in the world.</h1><p>Read it alongside the rest of the story.</p><Link href={`/stories/${draft.story_id}`} className="button primary">Read the story<ArrowRight size={16}/></Link></div>;
  const images = draft.attachments.filter(a => a.mime_type.startsWith("image/"));
  const isAI = draft.source === "ai_generated";
  const promptPanels = draft.ai_data?.panels || [];
  return <div className="studio-page"><BackLink href={`/stories/${draft.story_id}`}>Back to {draft.story.title}</BackLink><div className="page-heading"><div><span className="eyebrow">CHAPTER {String(draft.base_version + 1).padStart(2, "0")} · CHAPTER STUDIO</span><h1>A little polish. All your own.</h1><p>Read it through, make your edits, and decide when it&apos;s ready.</p></div><span className="private-badge"><LockKeyhole size={14}/>Private draft</span></div>
    {isAI ? <AINotice model={draft.ai_data?.model || "configured text model"} mocked={draft.ai_data?.is_test_fixture}/> : <DemoNotice studio/>}
    {isAI && draft.ai_data?.memory && <details className="chapter-notes"><summary>Chapter summary and scene notes</summary><p>{draft.ai_data.memory.summary.synopsis}</p>{draft.ai_data.scenes?.map((scene, i) => <p key={i}><strong>{scene.location}</strong> · {scene.description}</p>)}{draft.ai_data.dialogue?.map((line, i) => <p key={`line-${i}`}><strong>{line.speaker}:</strong> {line.text}</p>)}<small>These notes describe the generated version. Summary and canon are refreshed from your final edits before publication.</small></details>}
    {draft.parent_draft_id && <p className="version-note">A separate draft version. <Link href={`/studio/${draft.parent_draft_id}`}>Open the previous saved version</Link>.</p>}
    {draft.generation_error && <div className="error" role="alert">{draft.generation_error.includes("quota") ? "The generation limit was reached." : draft.generation_error === "timeout" ? "The text provider took too long to respond." : "The last AI generation did not complete."} Your saved contribution and draft are intact. {health?.ai_enabled && <button className="text-button" onClick={() => { setPanelIndex(null); setConfirm("ai"); }}>Retry AI generation</button>}</div>}
    {draft.image_generation_error && <div className="error" role="alert">The last local SDXL image attempt did not complete. Descriptions, uploaded media and any previous panel image are preserved. Check the local service, then retry the panel image action.</div>}
    {busy === "image" && <div className="generation-progress" role="status"><LoaderCircle size={19} className="spinner"/><div><strong>Generating one local panel image…</strong><p>Your previous version stays intact. No paid image API is used.</p></div></div>}
    {busy === "ai" && <div className="generation-progress" role="status"><LoaderCircle size={19} className="spinner"/><div><strong>{panelIndex === null ? "Creating a new chapter version…" : "Regenerating one panel description…"}</strong><p>Your saved draft and uploaded media are preserved.</p></div></div>}
    {draft.story.version !== draft.base_version && <p className="error conflict-banner" role="alert">A new chapter has been published since this draft began. Keep a copy of your text, <Link href={`/stories/${draft.story_id}`}>read the latest chapter</Link>, and start a new contribution. This draft cannot overwrite the current story.</p>}
    <div className="studio-grid"><section className="studio-editor editor-card"><div className="studio-toolbar"><div className="feed-tabs" role="tablist" aria-label="Editor view"><button role="tab" aria-selected={view === "edit"} className={view === "edit" ? "selected" : ""} onClick={() => setView("edit")}><PenLine size={16}/>Edit chapter</button><button role="tab" aria-selected={view === "preview"} className={view === "preview" ? "selected" : ""} onClick={() => setView("preview")}><Eye size={16}/>Preview</button></div><span className="save-state">{saved ? <><Check size={13}/>Saved</> : "Unsaved changes"}</span></div>
      {view === "edit" ? <div className="form-stack"><label>Chapter title<input value={title} maxLength={100} onChange={e => { setTitle(e.target.value); setSaved(false); }} aria-label="Chapter title"/></label><label>Narrative<textarea value={narrative} rows={19} maxLength={12000} onChange={e => { setNarrative(e.target.value); setSaved(false); }} aria-label="Chapter narrative"/><span className="character-count">{narrative.length.toLocaleString()} / 12,000</span></label></div> : <article className="studio-prose"><span className="chapter-kicker">CHAPTER {String(draft.base_version + 1).padStart(2, "0")}</span><h2>{title}</h2>{narrative ? narrative.split(/\n\s*\n/).map((p, i) => <p key={i}>{p}</p>) : <p className="muted">Add your narrative in the editor before publishing.</p>}</article>}
      <div className="studio-editor-footer">{isAI ? <button className="button secondary small" disabled={!!busy || !health?.ai_enabled} onClick={() => { setPanelIndex(null); setConfirm("ai"); }}><RefreshCw size={15}/>Regenerate with AI</button> : <button className="button secondary small" onClick={() => setConfirm("regenerate")} disabled={!!busy}><RefreshCw size={15}/>Regenerate preview</button>}{!isAI && health?.ai_enabled ? <button className="button secondary small" disabled={!!busy} onClick={() => { setPanelIndex(null); setConfirm("ai"); }}><Sparkles size={15}/>Generate with AI</button> : <span>{isAI ? "Creates a separate saved version" : "Demo reset · no AI generation"}</span>}</div>
    </section><aside className="studio-panels"><div className="panel-heading"><h3><ImageIcon size={17}/>Comic panels</h3><span className="subtle-badge">{promptPanels.length ? `${promptPanels.length} descriptions` : images.length ? `${images.length} uploaded` : "Descriptions only"}</span></div>
      {images.length > 0 && <div className="studio-panel-images">{images.map((a, i) => <figure key={a.id}><span className="panel-number">UPLOADED IMAGE {String(i + 1).padStart(2, "0")}</span><Media item={a} privateFile/><figcaption>Your uploaded image · {a.filename}</figcaption></figure>)}</div>}
      {promptPanels.length > 0 ? <ComicDescriptions panels={promptPanels} busy={!!busy} privateImages regenerate={health?.ai_enabled ? index => { setPanelIndex(index); setConfirm("ai"); } : undefined} generateImage={health?.image_generation?.enabled ? index => { setPanelIndex(index); setConfirm("image"); } : undefined}/> : !images.length && <div className="panel-placeholder"><div className="placeholder-panel"><img src={draft.story.cover_url} alt="Story cover"/><span>Cover artwork only</span></div><h3>Your imagination, in frames.</h3><p>Generate with AI to create panel descriptions, then optionally render images with a configured local SDXL service. This cover is not a generated panel.</p></div>}
      {draft.attachments.filter(a => !a.mime_type.startsWith("image/")).map(a => <Media key={a.id} item={a} privateFile/>)}
      <p className="panel-help">{health?.image_generation?.enabled ? "Local SDXL is configured; availability is checked when you generate. One image at a time. " : "Local SDXL is disabled. Panel descriptions remain available. "}Review images and descriptions after editing. Uploaded media stays as-is. No paid image service is used.</p>
    </aside></div>
    {problem && <div className="error" role="alert">{problem} <Link href={`/stories/${draft.story_id}`}>Read the latest story</Link>.</div>}
    <div className="publish-bar"><span><LockKeyhole size={15}/>Only you can see this chapter until you publish.</span><div><button className="button secondary" disabled={!!busy || !title.trim()} onClick={() => void action("save")}><Save size={16}/>{busy === "save" ? "Saving…" : "Save draft"}</button><button className="button primary" disabled={!!busy || !title.trim() || !narrative.trim() || draft.story.version !== draft.base_version} onClick={() => setConfirm("publish")}>Approve & publish<ArrowRight size={17}/></button></div></div>
    {confirm === "publish" && <Modal title="Ready for the next page?" close={close}><p className="muted">Your chapter, <strong>{title}</strong>, will become chapter {draft.base_version + 1} of <strong>{draft.story.title}</strong>. Everyone will be able to read it and continue the story.</p><div className="confirmation-note"><BookOpen size={20}/><span>Published chapters are permanent. Review your words and attachments first. Edited AI chapters are analyzed before publishing so the Story Bible reflects your final version.</span></div><div className="modal-actions"><button className="button secondary" disabled={!!busy} onClick={close}>Keep editing</button><button className="button primary" disabled={!!busy} onClick={() => void action("publish")}>{busy === "publish" ? "Checking and publishing…" : "Publish chapter"}<Check size={16}/></button></div></Modal>}
    {confirm === "ai" && <Modal title={panelIndex === null ? "Create a new AI draft version?" : `Regenerate panel ${panelIndex + 1} description?`} close={close}><p className="muted">Your current edits will be saved. {providerName} will create {panelIndex === null ? "a separate chapter draft from your original idea" : "a new draft version with only this panel description replaced"}. Your previous saved version and uploaded images stay available. A changed description needs a new panel image.</p><p className="confirmation-note">This sends necessary story context and your idea or reviewed chapter to {providerName}. {textProviderDisclosure(health)} Local image generation is a separate action.</p><div className="modal-actions"><button className="button secondary" disabled={!!busy} onClick={close}>Keep editing</button><button className="button primary" disabled={!!busy} onClick={() => void action("ai")}><Sparkles size={16}/>{busy ? "Generating…" : "Generate with AI"}</button></div></Modal>}
    {confirm === "image" && panelIndex !== null && <Modal title={`Generate panel ${panelIndex + 1} locally?`} close={close}><p className="muted">Your edits will be saved. The configured local SDXL service will render one image at {health?.image_generation?.width}×{health?.image_generation?.height}. This creates a new private draft version; previous images and uploaded media stay available.</p><p className="confirmation-note">Only this panel prompt and fictional appearance notes go to the local endpoint. No paid image service or Gemini call is used. If SDXL is offline or busy, keep the descriptions and retry later.</p><div className="modal-actions"><button className="button secondary" disabled={!!busy} onClick={close}>Keep editing</button><button className="button primary" disabled={!!busy} onClick={() => void action("image")}>{busy ? "Generating locally…" : "Generate image locally"}</button></div></Modal>}
    {confirm === "regenerate" && <Modal title="Reset your demo preview?" close={close}><p className="muted">The demo preview doesn&apos;t generate new text. This restores your original contribution and default chapter title, replacing your current edits.</p><div className="modal-actions"><button className="button secondary" disabled={!!busy} onClick={close}>Keep my edits</button><button className="button primary" disabled={!!busy} onClick={() => void action("regenerate")}>{busy ? "Resetting…" : "Reset preview"}</button></div></Modal>}
  </div>;
}
