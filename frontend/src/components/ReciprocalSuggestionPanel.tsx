/**
 * ReciprocalSuggestionPanel — inline suggestion panel for Address-Map pair editing.
 *
 * Conforms to 08-UI-SPEC.md §ReciprocalSuggestionPanel:
 * - Appears inline below the Address-Map row being edited (D-85)
 * - Heading "Reciprocal pair (auto-suggested)" in 12px semibold
 * - If reciprocal non-null: two PronounCombo inputs pre-filled + Confirm/Skip buttons
 * - If reciprocal null: "No known reciprocal…" message + Dismiss link
 * - Focus moved to panel heading on mount (accessibility)
 * - role="complementary"
 */
import { useEffect, useRef, useState } from "react";
import PronounCombo from "./PronounCombo";

interface ReciprocalPair {
  self_term: string;
  address_term: string;
}

interface ReciprocalSuggestionPanelProps {
  forwardSelfTerm: string;
  forwardAddressTerm: string;
  reciprocal: ReciprocalPair | null;
  onConfirm: (rec: ReciprocalPair) => void;
  onDismiss: () => void;
  selfTerms: string[];
  addressTerms: string[];
}

export default function ReciprocalSuggestionPanel({
  reciprocal,
  onConfirm,
  onDismiss,
  selfTerms,
  addressTerms,
}: ReciprocalSuggestionPanelProps) {
  const headingRef = useRef<HTMLHeadingElement>(null);

  // Editable reciprocal state (pre-filled from suggestion, user can adjust)
  const [recSelfTerm, setRecSelfTerm] = useState(reciprocal?.self_term ?? "");
  const [recAddressTerm, setRecAddressTerm] = useState(
    reciprocal?.address_term ?? "",
  );

  // Move focus to panel heading on mount (accessibility)
  useEffect(() => {
    headingRef.current?.focus();
  }, []);

  return (
    <div
      role="complementary"
      className="bg-bg-surface border border-[#2d3148] rounded p-4 mt-2"
    >
      <h3
        ref={headingRef}
        tabIndex={-1}
        className="text-xs font-semibold text-text-primary mb-3 focus:outline-none"
      >
        Reciprocal pair (auto-suggested)
      </h3>

      {reciprocal !== null ? (
        <div className="flex flex-col gap-3">
          <div className="flex gap-3 items-center">
            <div className="flex-1">
              <label className="text-xs text-text-muted block mb-1">
                Self term (reverse)
              </label>
              <PronounCombo
                value={recSelfTerm}
                onChange={setRecSelfTerm}
                terms={selfTerms}
                placeholder="Select…"
              />
            </div>
            <div className="flex-1">
              <label className="text-xs text-text-muted block mb-1">
                Address term (reverse)
              </label>
              <PronounCombo
                value={recAddressTerm}
                onChange={setRecAddressTerm}
                terms={addressTerms}
                placeholder="Select…"
              />
            </div>
          </div>
          <div className="flex items-center gap-4">
            <button
              type="button"
              className="text-xs text-accent"
              onClick={() =>
                onConfirm({
                  self_term: recSelfTerm,
                  address_term: recAddressTerm,
                })
              }
            >
              Confirm reciprocal
            </button>
            <button
              type="button"
              className="text-xs text-text-muted"
              onClick={onDismiss}
            >
              Skip — set manually later
            </button>
          </div>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          <p className="text-xs text-text-muted">
            No known reciprocal for this pair. Set the reverse pair manually.
          </p>
          <button
            type="button"
            className="text-xs text-text-muted self-start"
            onClick={onDismiss}
          >
            Dismiss
          </button>
        </div>
      )}
    </div>
  );
}
