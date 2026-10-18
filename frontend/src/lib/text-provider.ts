import type { Health } from "./types";

export function textProviderName(health: Health | null | undefined) {
  return health?.ai?.mode === "amd" ? "AMD Token Factory" : health?.ai?.mode === "gemini" ? "Gemini" : "the configured text provider";
}

export function textProviderDisclosure(health: Health | null | undefined) {
  return health?.ai?.mode === "amd"
    ? "AMD Radeon Cloud processes this text under its API terms. Do not include sensitive personal information. Media files stay here."
    : "Google's unpaid tier may use inputs and outputs to improve its products. Don't include sensitive personal information. Media files stay here.";
}
