"use client";
import {useEffect, useRef, useState} from "react";
import type {ReadingState, Story} from "./types";
import {useResource} from "./use-resource";
import {post, errorMessage} from "./api";
import {useApp} from "@/components/providers";

export function useReading(story: Story | null, layout: string, onPage: (index: number, layout: string) => void) {
  const {user} = useApp();
  const resource = useResource<ReadingState>(story && user ? `/me/reading/${story.id}` : null);
  const [progress, setProgress] = useState<ReadingState | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const active = useRef(false);
  const resumed = useRef("");
  useEffect(() => {setProgress(resource.data?.user_id === user?.id && resource.data?.story_id === story?.id ? resource.data : null);}, [resource.data, user?.id, story?.id]);
  async function navigate(index: number, chosenLayout = layout, completed = false) {
    const chapter = story?.chapters?.[index];
    if (!chapter || active.current) return;
    active.current = true; setBusy(true); setError("");
    try {
      if (user) setProgress(await post<ReadingState>(`/me/reading/${story!.id}`, {chapter_id: chapter.id, layout: chosenLayout, completed}));
    } catch (e) {setError(errorMessage(e));} finally {active.current = false; setBusy(false);}
    onPage(index, chosenLayout);
    if (!completed) requestAnimationFrame(() => {
      const target = document.getElementById(`chapter-${chapter.id}`);
      target?.focus({preventScroll:true});
      target?.scrollIntoView({block: "start"});
    });
  }
  function resume() {
    if (!progress || !story?.chapters?.length) return;
    const position = progress.completed_position >= progress.position ? progress.completed_position + 1 : progress.position;
    void navigate(Math.min(position, story.chapters.length) - 1, progress.layout);
  }
  useEffect(() => {
    if (story && progress && location.hash === "#resume" && resumed.current !== story.id) {
      resumed.current = story.id;
      resume();
    }
  });
  return {progress, busy, error: error || resource.error, loading: resource.loading, navigate, resume};
}
