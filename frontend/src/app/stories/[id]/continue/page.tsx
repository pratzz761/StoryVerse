import { ContinueStory } from "@/components/continue-story";
import { AuthGate } from "@/components/auth-gate";
export const metadata = { title: "Continue the story" };
export default async function Page({ params }: { params: Promise<{id: string}> }) { return <AuthGate><ContinueStory id={(await params).id}/></AuthGate>; }
