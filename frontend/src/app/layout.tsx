import type { Metadata, Viewport } from "next";
import { Providers } from "@/components/providers";
import { Shell } from "@/components/shell";
import "./globals.css";

export const metadata: Metadata = { title: { default: "Explore · StoryVerse", template: "%s · StoryVerse" }, description: "A home for stories made together. Read, write, and discover where a little imagination can take you." };
export const viewport: Viewport = { themeColor: "#0B0B0F", width: "device-width", initialScale: 1 };
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="en" data-scroll-behavior="smooth"><body><Providers><Shell>{children}</Shell></Providers></body></html>;
}
