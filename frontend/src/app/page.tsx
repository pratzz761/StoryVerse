import { Suspense } from "react";
import { Explore } from "@/components/explore";
import { Loading } from "@/components/ui";
export default function Page() { return <Suspense fallback={<Loading/>}><Explore/></Suspense>; }
