import { ProfilePage } from "@/components/profile-page";
import { AuthGate } from "@/components/auth-gate";
export const metadata = { title: "My profile" };
export default function Page() { return <AuthGate><ProfilePage/></AuthGate>; }
