"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, BookOpen, Check, Feather, Users } from "lucide-react";
import { GENRES, type Attachment } from "@/lib/types";
import { post, errorMessage } from "@/lib/api";
import { Uploads } from "./uploads";
import { BackLink } from "./ui";
import { useApp } from "./providers";

export function StoryForm() {
  const router = useRouter();
  const { toast, health } = useApp();
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [uploading, setUploading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [text, setText] = useState("");
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (uploading || busy) return;
    const form = new FormData(event.currentTarget);
    setBusy(true); setError("");
    try {
      const result = await post<{id: string}>("/stories", { title: form.get("title"), genre: form.get("genre"), narrative: text, upload_ids: attachments.map(a => a.id) });
      toast("Your story has a beginning. Let's see where it goes.");
      router.push(`/stories/${result.id}`);
    } catch (e) { setError(errorMessage(e)); setBusy(false); }
  }
  return <div className="writing-page"><BackLink href="/">Back to Explore</BackLink><div className="page-heading"><div><span className="eyebrow">THE FIRST PAGE</span><h1>Every world starts somewhere.</h1><p>Set the scene. Leave the door open for someone else.</p></div></div>
    <div className="writing-grid"><form className="editor-card form-stack" onSubmit={submit}>
      <div className="form-row"><label className="title-field">Story title<input name="title" placeholder="Give your world a name" maxLength={100} required autoFocus/></label><label>Genre<select name="genre" defaultValue="Fantasy">{GENRES.map(g => <option key={g}>{g}</option>)}</select></label></div>
      <label>The beginning<span className="field-hint">A scene, a character, an unexpected question. Start with what you have.</span><textarea name="narrative" value={text} onChange={e => setText(e.target.value)} required maxLength={12000} rows={12} placeholder="It started with something no one could explain…"/><span className="character-count">{text.length.toLocaleString()} / 12,000</span></label>
      <div><label className="field-label">Add to the picture <span className="optional">Optional</span></label><p className="field-hint">Your first image becomes the story cover. Media is published as uploaded.</p><Uploads value={attachments} onChange={setAttachments} onBusy={setUploading}/></div>
      <label className="checkbox-label"><input type="checkbox" required/><span>I&apos;m ready to publish this opening chapter and invite others to continue it.</span></label>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="form-actions"><span><BookOpen size={15}/>{health?.mode === "demo" ? "Saved in your local demo workspace" : "Public once you create it"}</span><button className="button primary" disabled={busy || uploading}>{busy ? "Creating your story…" : "Create story"}<ArrowRight size={17}/></button></div>
    </form><aside className="writing-aside"><div className="aside-symbol"><Feather size={24}/></div><h3>A beginning, not a blueprint.</h3><p>The best collaborative stories leave a little room for surprise.</p><div className="writing-tip"><Check size={17}/><div><strong>Make us curious</strong><p>A small mystery goes a long way.</p></div></div><div className="writing-tip"><Users size={17}/><div><strong>Let others in</strong><p>Anyone signed in can add the next chapter.</p></div></div><div className="aside-divider"/><small>Your opening chapter uses your text and attachments as written. Contributors can continue it with AI when configured. Comic images are uploaded manually; generated panel descriptions are clearly labeled.</small></aside></div>
  </div>;
}
