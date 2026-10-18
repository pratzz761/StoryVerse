"use client";
import {useState} from "react";
import {useResource} from "@/lib/use-resource";
import {post,errorMessage} from "@/lib/api";
import {ErrorState,Loading} from "./ui";
type Report={id:string;story_id:string;title:string;reason:string;details:string;status:string;is_hidden:boolean};
export function Moderation() {
 const {data,error,loading,reload}=useResource<Report[]>("/moderation/reports");
 const [busy,setBusy]=useState(false),[problem,setProblem]=useState("");
 if(loading)return <Loading label="Loading reports…"/>;
 if(error)return <ErrorState message={error} retry={reload}/>;
 return <div className="writing-page form-stack"><h1>Community reports</h1><p className="muted">Assigned moderators can review reports and hide or restore public stories. Hiding a story also removes its referenced media from public reading.</p>
 {problem && <p role="alert" className="error">{problem}</p>}
 {!data?.length && <p>No reports to review.</p>}
 {data?.map(report=><section key={report.id} className="editor-card form-stack"><h2>{report.title}</h2><p>{report.reason} · {report.status}</p><p>{report.details}</p>
 <form className="form-stack" onSubmit={async event=>{event.preventDefault();const reason=String(new FormData(event.currentTarget).get("reason"));setBusy(true);setProblem("");
 try{await post(`/moderation/stories/${report.story_id}`,{hidden:!report.is_hidden,reason});reload();}catch(e){setProblem(errorMessage(e));}finally{setBusy(false);}}}>
 <label>Moderation reason<input name="reason" required minLength={5} maxLength={500}/></label>
 <button className="button secondary" disabled={busy}>{report.is_hidden ? "Restore public story" : "Hide public story"}</button>
 </form></section>)}
 </div>;
}
