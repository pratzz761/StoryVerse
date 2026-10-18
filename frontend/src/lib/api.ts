import { createClient, type SupabaseClient } from "@supabase/supabase-js";

let client: SupabaseClient | null | undefined;
export function supabase() {
  if (client !== undefined) return client;
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  client = url && key ? createClient(url, key) : null;
  return client;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  const session = await supabase()?.auth.getSession();
  if (session?.data.session) headers.set("Authorization", `Bearer ${session.data.session.access_token}`);
  if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  let response: Response;
  try {
    response = await fetch(`/api${path}`, { ...options, headers, cache: "no-store" });
  } catch {
    throw new ApiError(0, "Couldn't reach StoryVerse. Check that the API is running and try again.");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = body?.detail;
    throw new ApiError(response.status, typeof detail === "string" ? detail : Array.isArray(detail) ? detail.map((e: {msg: string}) => e.msg).join(". ") : "Couldn't complete this request. Please try again.");
  }
  return response.json();
}

export async function privateMedia(url: string): Promise<string> {
  const session = await supabase()?.auth.getSession();
  const response = await fetch(url, { headers: session?.data.session ? { Authorization: `Bearer ${session.data.session.access_token}` } : {} });
  if (!response.ok) throw new Error("Unable to load attachment");
  return URL.createObjectURL(await response.blob());
}

export const post = <T,>(path: string, data: unknown) => request<T>(path, { method: "POST", body: JSON.stringify(data) });
export const patch = <T,>(path: string, data: unknown) => request<T>(path, { method: "PATCH", body: JSON.stringify(data) });
export const errorMessage = (error: unknown) => error instanceof Error ? error.message : "Something went wrong. Please try again.";
export type ImageJob = {id?: string; job_id?: string; status?: string; detail?: string};
export async function waitImageJob(initial: ImageJob, signal?: AbortSignal): Promise<{id: string}> {
  if (initial.id) return {id:initial.id};
  if (!initial.job_id) throw new Error("The image job response was incomplete. Your draft is saved.");
  const deadline = Date.now() + 7 * 60 * 1000;
  while (!signal?.aborted && Date.now() < deadline) {
    const job = await request<ImageJob>(`/image-jobs/${initial.job_id}`, {signal});
    if (job.status === "succeeded" && job.id) return {id:job.id};
    if (job.status === "failed") throw new Error(job.detail || "The image worker failed. Your previous draft is safe.");
    await new Promise(resolve => setTimeout(resolve, 3000));
  }
  throw new Error("Image generation is still pending. Reopen this saved draft to check its result.");
}
export function dateLabel(date: string) { return new Date(date).toLocaleDateString("en", { month: "short", day: "numeric", year: "numeric" }); }
