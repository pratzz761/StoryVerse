"use client";
import { ImageOff, ImageIcon, RefreshCw, Sparkles } from "lucide-react";
import type { ComicPrompt } from "@/lib/types";
import { Media } from "./ui";

export function ComicDescriptions({ panels, regenerate, generateImage, privateImages = false, busy }: { panels: ComicPrompt[]; regenerate?: (index: number) => void; generateImage?: (index: number) => void; privateImages?: boolean; busy?: boolean }) {
  return <div className="description-grid" data-testid="comic-descriptions">{panels.map((panel, i) => <figure className="prompt-panel" key={i}>
    <div className="prompt-panel-heading">{panel.image ? <ImageIcon size={17}/> : <ImageOff size={17}/>}<span>PANEL {String(i + 1).padStart(2, "0")}</span>{regenerate && <button type="button" className="icon-button" aria-label={`Regenerate panel ${i + 1} description`} disabled={busy} onClick={() => regenerate(i)}><RefreshCw size={14}/></button>}</div>
    {panel.image && <div className="generated-panel-image"><Media item={{id:panel.image.upload_id, filename:`Panel ${i + 1} · local SDXL`,mime_type:panel.image.mime_type,size_bytes:0,url:`/api/uploads/${panel.image.upload_id}/file`}} privateFile={privateImages}/></div>}
    <p>{panel.description}</p>{panel.caption && <blockquote>{panel.caption}</blockquote>}
    <div className="prompt-details"><span>{panel.location}</span><span>{panel.camera}</span></div>
    <figcaption>{panel.image ? panel.image.is_test_fixture ? "Mocked SDXL test image · No local inference" : "Generated locally with SDXL" : "Placeholder · Panel description · No image generated"}</figcaption>
    {generateImage && <button className="button secondary small panel-image-action" type="button" disabled={busy} aria-label={`${panel.image ? "Regenerate" : "Generate"} panel ${i + 1} image`} onClick={() => generateImage(i)}><ImageIcon size={14}/>{panel.image ? "Regenerate image" : "Generate image"}</button>}
  </figure>)}</div>;
}

export function AINotice({ model, mocked }: { model: string; mocked?: boolean }) {
  return <div className="demo-notice ai-notice"><span className="notice-icon"><Sparkles size={17}/></span><div><strong>{mocked ? "AI test fixture · No live text-model call" : "AI-generated draft · Review before publishing"}</strong><p>{mocked ? "This isolated text response is mocked. It is not a real model result." : `Text generated with ${model}. Check story facts, edit freely, and approve the final chapter. Local SDXL artwork is optional; descriptions remain available without it.`}</p></div></div>;
}
