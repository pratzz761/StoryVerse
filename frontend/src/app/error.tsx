"use client";
import { ErrorState } from "@/components/ui";
export default function Error({ reset }: { reset: () => void }) { return <ErrorState message="This page couldn't load. Please try again." retry={reset}/>; }
