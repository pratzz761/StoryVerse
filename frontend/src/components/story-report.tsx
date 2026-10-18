"use client";
import Link from "next/link";
import {useState} from "react";
import {Modal, useApp} from "./providers";
import {post, errorMessage} from "@/lib/api";

export function StoryReport({storyId}: {storyId: string}) {
  const {health, user, openAuth, toast} = useApp();
  const [open,setOpen] = useState(false), [busy,setBusy] = useState(false), [error,setError] = useState("");
  return <div className="small-text"><Link href="/guidelines">Community guidelines</Link>{health?.mode === "supabase" && <>
    {" · "}<button className="text-button" onClick={() => user ? setOpen(true) : openAuth()}>Report story</button></>}
    {open && <Modal title="Report this story" close={() => setOpen(false)}>
      <p className="muted">Reports are private. A moderator can remove the story from public reading without deleting its history.</p>
      <form className="form-stack" onSubmit={async event => {
        event.preventDefault(); const data=new FormData(event.currentTarget);setBusy(true);setError("");
        try {await post(`/stories/${storyId}/reports`,{reason:data.get("reason"),details:data.get("details")});setOpen(false);toast("Report received. A moderator will review it.");}
        catch(e){setError(errorMessage(e));}finally{setBusy(false);}
      }}>
        <label>Reason<select name="reason"><option value="spam">Spam</option><option value="harassment">Harassment</option><option value="sexual_content">Sexual content</option><option value="violence">Violence</option><option value="privacy">Private information</option><option value="copyright">Copyright</option><option value="other">Other</option></select></label>
        <label>Details<textarea name="details" maxLength={1000} rows={4}/></label>
        {error && <p role="alert" className="error">{error}</p>}<button className="button primary" disabled={busy}>{busy ? "Sending…" : "Submit report"}</button>
      </form>
    </Modal>}
  </div>;
}
