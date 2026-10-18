import { StoryForm } from "@/components/story-form";
import { AuthGate } from "@/components/auth-gate";
export const metadata = { title: "Create a story" };
export default function Page() { return <AuthGate><StoryForm/></AuthGate>; }
