import { Drafts } from "@/components/drafts";
import { AuthGate } from "@/components/auth-gate";
export const metadata = { title: "Drafts" };
export default function Page() { return <AuthGate><Drafts/></AuthGate>; }
