import { Studio } from "@/components/studio";
import { AuthGate } from "@/components/auth-gate";
export const metadata = { title: "Chapter Studio" };
export default async function Page({ params }: { params: Promise<{id: string}> }) { return <AuthGate><Studio id={(await params).id}/></AuthGate>; }
