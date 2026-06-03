/**
 * SubtitleBadge — reusable audio/subtitle language badge component.
 *
 * Design decisions:
 *  - D-06 (14-UI-SPEC.md §Badge Color Token Mapping): colors expressed ONLY as CSS variable
 *    tokens + Tailwind utility classes; never raw hex.
 *  - D-07 (14-UI-SPEC.md §SubtitleBadge Component Contract): non-color shape cue (Volume2
 *    icon for audio, filled dot for source/vi) + aria-label on each badge for accessibility.
 *  - 14-UI-SPEC.md §SubtitleBadge Component Contract: label format, tooltip, color classes.
 *
 * Place: src/components/ (hand-written) — NOT src/components/ui/ (vendor-only invariant).
 */
import { Volume2 } from "lucide-react";
import { Badge } from "./ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "./ui/tooltip";

export interface SubtitleBadgeProps {
  /** ISO-639-1 two-letter code; displayed as uppercase (e.g. "VI", "EN", "KO"). */
  code2: string;
  /** Hearing-impaired flag — appends ":HI" to the label. */
  hi?: boolean;
  /** Forced-subtitle flag — appends ":Forced" to the label. */
  forced?: boolean;
  /** Badge variant: audio track (blue), source subtitle (amber), or VI subtitle (purple). */
  type: "audio" | "source" | "vi";
}

/** Static code2 → human-readable language name map for aria-labels.
 *  Falls back to the raw code2 string (uppercased) for unknown codes. */
const LANG_NAMES: Record<string, string> = {
  ko: "Korean",
  en: "English",
  vi: "Vietnamese",
  zh: "Chinese",
  "zh-hant": "Chinese Traditional",
  ja: "Japanese",
  fr: "French",
  es: "Spanish",
  th: "Thai",
  de: "German",
  it: "Italian",
  pt: "Portuguese",
  ru: "Russian",
  ar: "Arabic",
};

/** Color class per badge type (CSS variable tokens only — D-06). */
const COLOR_CLASSES: Record<SubtitleBadgeProps["type"], string> = {
  audio: "bg-blue-700/80 text-white border-transparent",
  source: "bg-amber-600/80 text-white border-transparent",
  vi: "bg-[hsl(var(--primary))]/80 text-primary-foreground border-transparent",
};

/**
 * A compact badge for an audio track or subtitle track language code.
 *
 * - audio: blue background, Volume2 lucide icon prefix (shape cue per D-07)
 * - source: amber background, filled dot prefix
 * - vi: purple (primary) background, filled dot prefix
 *
 * Each badge is wrapped in a Tooltip showing the full aria-label text.
 */
export function SubtitleBadge({ code2, hi, forced, type }: SubtitleBadgeProps) {
  // --- Label construction ---
  const upperCode = code2.toUpperCase();
  const label = [upperCode, hi ? ":HI" : null, forced ? ":Forced" : null]
    .filter(Boolean)
    .join("");

  // --- Aria-label construction ---
  const langName = LANG_NAMES[code2.toLowerCase()] ?? upperCode;
  let ariaLabel: string;
  if (type === "audio") {
    ariaLabel = `${langName} audio`;
  } else if (type === "source") {
    const flags = [hi ? "hearing impaired" : null, forced ? "forced" : null]
      .filter(Boolean)
      .join(", ");
    ariaLabel = `${langName} source subtitle${flags ? `, ${flags}` : ""}`;
  } else {
    // vi
    const flags = [hi ? "hearing impaired" : null, forced ? "forced" : null]
      .filter(Boolean)
      .join(", ");
    ariaLabel = `Vietnamese subtitle${flags ? `, ${flags}` : ""}`;
  }

  // --- Shape cue (D-07 mandatory non-color distinction) ---
  const shapePrefix =
    type === "audio" ? (
      // Volume2 lucide icon for audio — distinct from dot-prefixed subtitle badges
      <Volume2 size={10} aria-hidden className="inline mr-0.5" />
    ) : (
      // Filled dot for source and vi — same shape, distinguished by color (amber vs purple)
      <span aria-hidden className="mr-0.5 text-[8px]">
        ●
      </span>
    );

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <Badge
            className={`${COLOR_CLASSES[type]} text-xs px-1.5 py-0.5 inline-flex items-center gap-0.5 cursor-default`}
            aria-label={ariaLabel}
          >
            {shapePrefix}
            {label}
          </Badge>
        </TooltipTrigger>
        <TooltipContent>{ariaLabel}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
