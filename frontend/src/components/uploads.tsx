"use client";
import { useRef, useState } from "react";
import { ImagePlus, Mic, Film, Upload, X, FileAudio, FileImage, FileVideo, LoaderCircle } from "lucide-react";
import { request, errorMessage } from "@/lib/api";
import type { Attachment } from "@/lib/types";

export function Uploads({ value, onChange, onBusy }: { value: Attachment[]; onChange: (v: Attachment[]) => void; onBusy: (v: boolean) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [drag, setDrag] = useState(false);
  async function add(files: FileList | File[]) {
    if (busy) return;
    setError("");
    const selected = Array.from(files);
    if (selected.length + value.length > 6) { setError("You can add up to 6 attachments."); return; }
    if (selected.some(f => f.size > 20 * 1024 * 1024)) { setError("Each file must be 20 MB or smaller."); return; }
    setBusy(true); onBusy(true);
    const uploaded = [...value];
    try {
      for (const file of selected) {
        const form = new FormData(); form.append("file", file);
        uploaded.push(await request<Attachment>("/uploads", { method: "POST", body: form }));
        onChange([...uploaded]);
      }
    } catch (e) { setError(errorMessage(e)); }
    finally { setBusy(false); onBusy(false); if (input.current) input.current.value = ""; }
  }
  return <div className="upload-component">
    <input ref={input} type="file" multiple className="sr-only" accept="image/jpeg,image/png,image/webp,image/gif,audio/mpeg,audio/wav,audio/ogg,audio/mp4,audio/webm,video/mp4,video/webm" aria-label="Upload attachments" onChange={e => { if (e.target.files) void add(e.target.files); }}/>
    <button type="button" className={`upload-zone ${drag ? "dragging" : ""}`} disabled={busy || value.length >= 6} onClick={() => input.current?.click()} onDragOver={e => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)} onDrop={e => { e.preventDefault(); setDrag(false); void add(e.dataTransfer.files); }}>
      {busy ? <LoaderCircle className="spinner" size={24}/> : <Upload size={24}/>}<strong>{busy ? "Uploading your inspiration…" : "Drop a little inspiration here"}</strong><span>Choose images, audio, or video · 20 MB per file · Up to 6 files</span><div className="upload-types"><span><ImagePlus size={15}/>Image</span><span><Mic size={15}/>Audio</span><span><Film size={15}/>Video</span></div>
    </button>
    {value.length > 0 && <ul className="attachment-list">{value.map(item => { const Icon = item.mime_type.startsWith("image/") ? FileImage : item.mime_type.startsWith("audio/") ? FileAudio : FileVideo; return <li key={item.id}><Icon size={18}/><span>{item.filename}<small>{(item.size_bytes / 1024 / 1024).toFixed(2)} MB</small></span><button type="button" className="icon-button" disabled={busy} aria-label={`Remove ${item.filename}`} onClick={() => onChange(value.filter(v => v.id !== item.id))}><X size={16}/></button></li>; })}</ul>}
    {error && <p className="error" role="alert">{error}</p>}
  </div>;
}
