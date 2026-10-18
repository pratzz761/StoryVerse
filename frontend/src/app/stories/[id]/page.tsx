import { StoryRoom } from "@/components/story-room";
export const metadata = { title: "Story room" };
export default async function Page({ params }: { params: Promise<{ id: string }> }) { return <StoryRoom id={(await params).id}/>; }
