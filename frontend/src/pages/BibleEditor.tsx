/**
 * BibleEditor page — Series Bible editor for one series (/bible/:seriesId).
 *
 * Conforms to 08-UI-SPEC.md §BibleEditor Page:
 * - Four tabs: Characters / Address Map / Terms / Register
 * - Inline row editing with LockBadge provenance
 * - PronounCombo for pronoun term selection (D-86)
 * - ReciprocalSuggestionPanel for address map editing (D-85)
 * - Hard-block on lock with empty term (D-87)
 * - FieldHistoryPanel inline expansion below rows
 *
 * Analog: Settings.tsx (load-on-mount, SectionCard, Toast pattern)
 */
import { useState, useEffect, useCallback, useRef } from "react";
import { useParams, Link } from "react-router-dom";
import { Clock, Pencil, Trash2 } from "lucide-react";
import {
  getSeriesBible,
  getPronouns,
  patchCharacter,
  patchAddressMapPair,
  patchRegister,
  addCharacter,
  addTerm,
  addAddressMapPair,
  deleteTerm,
  deleteAddressMapPair,
  type SeriesBibleDTO,
  type CharacterDTO,
  type AddressMapDTO,
  type TermDTO,
  type PronounsResponse,
} from "../api/client";
import LockBadge, { type LockState } from "../components/LockBadge";
import LockToggleButton from "../components/LockToggleButton";
import FieldHistoryPanel from "../components/FieldHistoryPanel";
import PronounCombo from "../components/PronounCombo";
import ReciprocalSuggestionPanel from "../components/ReciprocalSuggestionPanel";
import Toast from "../components/Toast";
import type { ToastState } from "../components/Toast";

// ── Helpers ───────────────────────────────────────────────────────────────────

function UnreachableBanner({ message }: { message: string }) {
  return (
    <div
      className="w-full mb-4 px-4 py-3 text-sm rounded"
      style={{ backgroundColor: "#451a03", color: "#fbbf24" }}
      role="alert"
    >
      {message}
    </div>
  );
}

function SectionCard({ children }: { children: React.ReactNode }) {
  return (
    <div className="bg-bg-surface border border-[#2d3148] rounded p-6 flex flex-col gap-4">
      {children}
    </div>
  );
}

interface TextFieldProps {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  disabled?: boolean;
}

function TextField({
  id,
  label,
  value,
  onChange,
  placeholder = "",
  disabled = false,
}: TextFieldProps) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-xs text-text-muted">
        {label}
      </label>
      <input
        id={id}
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        className="h-9 w-full bg-bg-surface border border-[#2d3148] rounded px-2 text-sm text-text-primary focus:outline-[#3b82f6] focus:outline-2 focus:outline-offset-2 disabled:opacity-60 disabled:cursor-not-allowed"
      />
    </div>
  );
}

type Tab = "characters" | "address_map" | "terms" | "register";

// ── Main page ─────────────────────────────────────────────────────────────────

export default function BibleEditor() {
  const { seriesId: seriesIdStr } = useParams<{ seriesId: string }>();
  const seriesId = Number(seriesIdStr ?? "0");

  const [bible, setBible] = useState<SeriesBibleDTO | null>(null);
  const [pronounsData, setPronounsData] = useState<PronounsResponse>({
    self_terms: [],
    address_terms: [],
    kinship_reciprocal: {},
  });
  const [unreachable, setUnreachable] = useState(false);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<Tab>("characters");
  const [toast, setToast] = useState<ToastState | null>(null);

  const showToast = useCallback((t: Omit<ToastState, "id">) => {
    setToast({ ...t, id: Date.now() });
  }, []);

  useEffect(() => {
    if (!seriesId) return;
    let cancelled = false;
    async function load() {
      try {
        const [b, p] = await Promise.all([
          getSeriesBible(seriesId),
          getPronouns(),
        ]);
        if (!cancelled) {
          setBible(b);
          setPronounsData(p);
          setUnreachable(false);
          setLoading(false);
        }
      } catch {
        if (!cancelled) {
          setUnreachable(true);
          setLoading(false);
        }
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [seriesId]);

  if (loading) {
    return (
      <div>
        <p className="text-sm text-text-muted">Loading…</p>
      </div>
    );
  }

  if (!bible) {
    return (
      <div>
        {unreachable && (
          <UnreachableBanner message="Could not load Bible for this series. Check the server logs." />
        )}
      </div>
    );
  }

  return (
    <div className="max-w-5xl">
      {/* Breadcrumb + header */}
      <div className="mb-2">
        <Link to="/bible" className="text-xs text-accent no-underline">
          ← Bible
        </Link>
      </div>
      <div className="flex items-center gap-3 mb-4">
        <h1 className="text-lg font-semibold text-text-primary">
          {bible.arr_kind}/{bible.arr_series_id}
        </h1>
        {bible.register && (
          <span className="text-xs text-text-muted">{bible.register}</span>
        )}
      </div>

      {unreachable && (
        <UnreachableBanner message="Could not load Bible for this series. Check the server logs." />
      )}

      {/* BibleTabBar */}
      <nav
        role="tablist"
        className="flex border-b border-[#2d3148] mb-4"
        aria-label="Bible sections"
      >
        {(
          [
            ["characters", "Characters"],
            ["address_map", "Address Map"],
            ["terms", "Terms"],
            ["register", "Register"],
          ] as [Tab, string][]
        ).map(([tab, label]) => (
          <button
            key={tab}
            role="tab"
            aria-selected={activeTab === tab}
            onClick={() => setActiveTab(tab)}
            className={[
              "h-10 px-4 text-sm focus:outline-none",
              activeTab === tab
                ? "text-text-primary border-b-2 border-[#3b82f6]"
                : "text-text-muted hover:text-text-primary border-b-2 border-transparent",
            ].join(" ")}
          >
            {label}
          </button>
        ))}
      </nav>

      {/* Tab content */}
      <div role="tabpanel">
        {activeTab === "characters" && (
          <CharactersSection
            seriesId={seriesId}
            bible={bible}
            setBible={setBible}
            showToast={showToast}
          />
        )}
        {activeTab === "address_map" && (
          <AddressMapSection
            seriesId={seriesId}
            bible={bible}
            setBible={setBible}
            pronounsData={pronounsData}
            showToast={showToast}
          />
        )}
        {activeTab === "terms" && (
          <TermsSection
            seriesId={seriesId}
            bible={bible}
            setBible={setBible}
            showToast={showToast}
          />
        )}
        {activeTab === "register" && (
          <RegisterSection
            seriesId={seriesId}
            bible={bible}
            setBible={setBible}
            showToast={showToast}
          />
        )}
      </div>

      <Toast toast={toast} onDismiss={() => setToast(null)} />
    </div>
  );
}

// ── Characters Section ────────────────────────────────────────────────────────

interface CharactersSectionProps {
  seriesId: number;
  bible: SeriesBibleDTO;
  setBible: React.Dispatch<React.SetStateAction<SeriesBibleDTO | null>>;
  showToast: (t: Omit<ToastState, "id">) => void;
}

function CharactersSection({
  seriesId,
  bible,
  setBible,
  showToast,
}: CharactersSectionProps) {
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editFields, setEditFields] = useState<{
    gender: string;
    rough_age: string;
    role: string;
  }>({ gender: "", rough_age: "", role: "" });
  const [historyOpenId, setHistoryOpenId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);

  // Add character form
  const [showAddForm, setShowAddForm] = useState(false);
  const [addFields, setAddFields] = useState({
    original_latin_name: "",
    gender: "",
    rough_age: "",
    role: "",
  });

  function startEdit(char: CharacterDTO) {
    setEditingId(char.id);
    setEditFields({
      gender: char.gender ?? "",
      rough_age: char.rough_age ?? "",
      role: char.role ?? "",
    });
    setHistoryOpenId(null);
  }

  function discardEdit() {
    setEditingId(null);
    setEditFields({ gender: "", rough_age: "", role: "" });
  }

  async function saveCharacter(char: CharacterDTO) {
    setSaving(true);
    // WR-05: track committed state outside try/catch so partial-save errors can
    // update the UI to the last authoritative server response before showing toast.
    let updatedChar: CharacterDTO = char;
    let partialSave = false;
    try {
      for (const [field, value] of Object.entries(editFields)) {
        if (value !== (char[field as keyof CharacterDTO] ?? "")) {
          // Each PATCH may throw — catch below shows the error toast and stops the loop.
          const result = await patchCharacter(seriesId, char.id, {
            field,
            value,
          });
          // Track the latest server-authoritative response so the UI reflects committed state.
          updatedChar = result;
        }
      }
    } catch {
      // WR-05: partial save — surface the error and keep the edit form open for retry.
      partialSave = true;
      showToast({
        message: "Some fields failed to save. Successfully-saved fields are shown; retry remaining changes.",
        variant: "error",
      });
    } finally {
      setSaving(false);
    }
    // Always update the UI to the last committed server response (works for both full and partial saves).
    if (updatedChar !== char) {
      setBible((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          characters: prev.characters.map((c) =>
            c.id === char.id ? updatedChar : c,
          ),
        };
      });
    }
    if (!partialSave) {
      setEditingId(null);
      showToast({ message: "Changes saved.", variant: "success" });
    }
  }

  async function toggleLock(char: CharacterDTO) {
    const isLocked = char.locked_fields.length > 0;
    const lockState = !isLocked;
    try {
      // Lock/unlock all fields together
      let updatedChar = char;
      for (const field of ["gender", "rough_age", "role"]) {
        const value = char[field as keyof CharacterDTO] ?? "";
        const result = await patchCharacter(seriesId, char.id, {
          field,
          value,
          lock: lockState,
        });
        updatedChar = result;
      }
      setBible((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          characters: prev.characters.map((c) =>
            c.id === char.id ? updatedChar : c,
          ),
        };
      });
      showToast({
        message: lockState ? "Field locked." : "Field unlocked.",
        variant: "success",
      });
    } catch {
      showToast({
        message: "Failed to save changes. Check the server logs.",
        variant: "error",
      });
    }
  }

  async function handleAddCharacter() {
    if (!addFields.original_latin_name.trim()) return;
    try {
      const newChar = await addCharacter(seriesId, {
        original_latin_name: addFields.original_latin_name.trim(),
        gender: addFields.gender || undefined,
        rough_age: addFields.rough_age || undefined,
        role: addFields.role || undefined,
      });
      setBible((prev) => {
        if (!prev) return prev;
        // newChar is a CharacterDTO (from addCharacter API)
        return { ...prev, characters: [newChar, ...prev.characters] };
      });
      setShowAddForm(false);
      setAddFields({ original_latin_name: "", gender: "", rough_age: "", role: "" });
      showToast({ message: "Character added.", variant: "success" });
    } catch {
      showToast({
        message: "Failed to add character.",
        variant: "error",
      });
    }
  }

  return (
    <SectionCard>
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold text-text-primary">
          Characters
        </h2>
        <button
          type="button"
          className="text-sm text-accent px-3 py-1 rounded border border-[#3b82f6] hover:bg-[#1e3a5f]"
          onClick={() => setShowAddForm(true)}
        >
          Add Character
        </button>
      </div>

      {showAddForm && (
        <div className="bg-bg-base border border-[#2d3148] rounded p-3 flex flex-wrap gap-3 items-end">
          <div className="flex-1 min-w-32">
            <label className="text-xs text-text-muted block mb-1">
              Name
            </label>
            <input
              type="text"
              autoFocus
              value={addFields.original_latin_name}
              onChange={(e) =>
                setAddFields((f) => ({
                  ...f,
                  original_latin_name: e.target.value,
                }))
              }
              className="h-9 w-full bg-bg-surface border border-[#2d3148] rounded px-2 text-sm text-text-primary focus:outline-[#3b82f6] focus:outline-2 focus:outline-offset-2"
            />
          </div>
          <div>
            <label className="text-xs text-text-muted block mb-1">
              Gender
            </label>
            <select
              value={addFields.gender}
              onChange={(e) =>
                setAddFields((f) => ({ ...f, gender: e.target.value }))
              }
              className="h-9 bg-bg-surface border border-[#2d3148] rounded px-2 text-sm text-text-primary focus:outline-[#3b82f6] focus:outline-2 focus:outline-offset-2"
            >
              <option value="">—</option>
              <option value="male">male</option>
              <option value="female">female</option>
              <option value="unknown">unknown</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-text-muted block mb-1">
              Age
            </label>
            <input
              type="text"
              value={addFields.rough_age}
              onChange={(e) =>
                setAddFields((f) => ({ ...f, rough_age: e.target.value }))
              }
              className="h-9 w-20 bg-bg-surface border border-[#2d3148] rounded px-2 text-sm text-text-primary focus:outline-[#3b82f6] focus:outline-2 focus:outline-offset-2"
            />
          </div>
          <div className="flex-1 min-w-32">
            <label className="text-xs text-text-muted block mb-1">
              Role
            </label>
            <input
              type="text"
              value={addFields.role}
              onChange={(e) =>
                setAddFields((f) => ({ ...f, role: e.target.value }))
              }
              className="h-9 w-full bg-bg-surface border border-[#2d3148] rounded px-2 text-sm text-text-primary focus:outline-[#3b82f6] focus:outline-2 focus:outline-offset-2"
            />
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              className="text-sm text-accent"
              onClick={handleAddCharacter}
            >
              Add Character
            </button>
            <button
              type="button"
              className="text-sm text-text-muted"
              onClick={() => setShowAddForm(false)}
            >
              Discard
            </button>
          </div>
        </div>
      )}

      {bible.characters.length === 0 ? (
        <p className="text-xs text-text-muted">
          No characters. Click Add Character to add the first one.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-[#2d3148]">
                <th
                  scope="col"
                  className="px-3 py-2 text-left text-xs text-text-muted font-normal"
                  style={{ width: "22%" }}
                >
                  Name
                </th>
                <th
                  scope="col"
                  className="px-3 py-2 text-left text-xs text-text-muted font-normal"
                  style={{ width: "12%" }}
                >
                  Gender
                </th>
                <th
                  scope="col"
                  className="px-3 py-2 text-left text-xs text-text-muted font-normal"
                  style={{ width: "10%" }}
                >
                  Age
                </th>
                <th
                  scope="col"
                  className="px-3 py-2 text-left text-xs text-text-muted font-normal"
                  style={{ width: "28%" }}
                >
                  Role
                </th>
                <th
                  scope="col"
                  className="px-3 py-2 text-left text-xs text-text-muted font-normal"
                  style={{ width: "14%" }}
                >
                  Lock
                </th>
                <th
                  scope="col"
                  className="px-3 py-2 text-left text-xs text-text-muted font-normal"
                  style={{ width: "7%" }}
                >
                  History
                </th>
                <th
                  scope="col"
                  className="px-3 py-2 text-left text-xs text-text-muted font-normal"
                  style={{ width: "7%" }}
                >
                  Actions
                </th>
              </tr>
            </thead>
            <tbody>
              {bible.characters.map((char, idx) => (
                <>
                  <tr
                    key={char.id}
                    className={[
                      "h-10 border-b border-[#2d3148]",
                      idx % 2 === 1 ? "bg-bg-stripe" : "",
                    ]
                      .filter(Boolean)
                      .join(" ")}
                  >
                    {editingId === char.id ? (
                      <>
                        <td className="px-3 text-sm text-text-primary">
                          {char.original_latin_name}
                        </td>
                        <td className="px-2">
                          <select
                            value={editFields.gender}
                            onChange={(e) =>
                              setEditFields((f) => ({
                                ...f,
                                gender: e.target.value,
                              }))
                            }
                            autoFocus
                            className="h-8 bg-bg-surface border border-[#2d3148] rounded px-1 text-xs text-text-primary focus:outline-[#3b82f6] focus:outline-2 focus:outline-offset-2 w-full"
                          >
                            <option value="">—</option>
                            <option value="male">male</option>
                            <option value="female">female</option>
                            <option value="unknown">unknown</option>
                          </select>
                        </td>
                        <td className="px-2">
                          <input
                            type="text"
                            value={editFields.rough_age}
                            onChange={(e) =>
                              setEditFields((f) => ({
                                ...f,
                                rough_age: e.target.value,
                              }))
                            }
                            className="h-8 w-full bg-bg-surface border border-[#2d3148] rounded px-1 text-xs text-text-primary focus:outline-[#3b82f6] focus:outline-2 focus:outline-offset-2"
                          />
                        </td>
                        <td className="px-2">
                          <input
                            type="text"
                            value={editFields.role}
                            onChange={(e) =>
                              setEditFields((f) => ({
                                ...f,
                                role: e.target.value,
                              }))
                            }
                            className="h-8 w-full bg-bg-surface border border-[#2d3148] rounded px-1 text-xs text-text-primary focus:outline-[#3b82f6] focus:outline-2 focus:outline-offset-2"
                          />
                        </td>
                        <td className="px-3">
                          <LockToggleButton
                            state={
                              (char.locked_fields.length > 0
                                ? "locked"
                                : "inference") as LockState
                            }
                            onToggle={() => toggleLock(char)}
                          />
                        </td>
                        <td className="px-3">
                          <button
                            type="button"
                            aria-label="View field history"
                            onClick={() =>
                              setHistoryOpenId(
                                historyOpenId === char.id ? null : char.id,
                              )
                            }
                            className="text-text-muted hover:text-accent"
                          >
                            <Clock size={14} />
                          </button>
                        </td>
                        <td className="px-3 flex items-center gap-2 h-10">
                          <button
                            type="button"
                            className="text-xs text-accent"
                            disabled={saving}
                            onClick={() => saveCharacter(char)}
                          >
                            {saving ? "Saving…" : "Save character"}
                          </button>
                          <button
                            type="button"
                            className="text-xs text-text-muted"
                            onClick={discardEdit}
                          >
                            Discard changes
                          </button>
                        </td>
                      </>
                    ) : (
                      <>
                        <td className="px-3 text-sm text-text-primary">
                          {char.original_latin_name}
                        </td>
                        <td className="px-3 text-xs text-text-primary">
                          {char.gender ?? "—"}
                        </td>
                        <td className="px-3 text-xs text-text-primary">
                          {char.rough_age ?? "—"}
                        </td>
                        <td className="px-3 text-xs text-text-primary">
                          {char.role ?? "—"}
                        </td>
                        <td className="px-3">
                          <div className="flex items-center gap-1">
                            <LockBadge
                              state={
                                char.locked_fields.length > 0
                                  ? "locked"
                                  : "inference"
                              }
                            />
                            <LockToggleButton
                              state={
                                (char.locked_fields.length > 0
                                  ? "locked"
                                  : "inference") as LockState
                              }
                              onToggle={() => toggleLock(char)}
                            />
                          </div>
                        </td>
                        <td className="px-3">
                          <button
                            type="button"
                            aria-label="View field history"
                            onClick={() =>
                              setHistoryOpenId(
                                historyOpenId === char.id ? null : char.id,
                              )
                            }
                            className="text-text-muted hover:text-accent"
                          >
                            <Clock size={14} />
                          </button>
                        </td>
                        <td className="px-3">
                          <button
                            type="button"
                            aria-label="Edit character"
                            onClick={() => startEdit(char)}
                            className="text-text-muted hover:text-accent"
                          >
                            <Pencil size={14} />
                          </button>
                        </td>
                      </>
                    )}
                  </tr>
                  {historyOpenId === char.id && (
                    <tr key={`${char.id}-history`}>
                      <td colSpan={7} className="px-3 pb-2">
                        <FieldHistoryPanel
                          seriesId={seriesId}
                          entityType="character"
                          entityId={char.id}
                          onClose={() => setHistoryOpenId(null)}
                        />
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </SectionCard>
  );
}

// ── Address Map Section ───────────────────────────────────────────────────────

interface AddressMapSectionProps {
  seriesId: number;
  bible: SeriesBibleDTO;
  setBible: React.Dispatch<React.SetStateAction<SeriesBibleDTO | null>>;
  pronounsData: PronounsResponse;
  showToast: (t: Omit<ToastState, "id">) => void;
}

interface PairEditState {
  selfTerm: string;
  addressTerm: string;
  selfTermChanged: boolean;
  addressTermChanged: boolean;
}

function AddressMapSection({
  seriesId,
  bible,
  setBible,
  pronounsData,
  showToast,
}: AddressMapSectionProps) {
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editFields, setEditFields] = useState<PairEditState>({
    selfTerm: "",
    addressTerm: "",
    selfTermChanged: false,
    addressTermChanged: false,
  });
  const [historyOpenId, setHistoryOpenId] = useState<number | null>(null);
  const [deleteConfirmId, setDeleteConfirmId] = useState<number | null>(null);
  const [showReciprocalForId, setShowReciprocalForId] = useState<number | null>(
    null,
  );
  const [saving, setSaving] = useState(false);

  // Add pair form
  const [showAddForm, setShowAddForm] = useState(false);
  const [addFields, setAddFields] = useState({
    speaker_character_id: "",
    addressee_character_id: "",
    self_term: "",
    address_term: "",
  });

  function characterName(charId: number): string {
    return (
      bible.characters.find((c) => c.id === charId)?.original_latin_name ??
      String(charId)
    );
  }

  function startEditPair(pair: AddressMapDTO) {
    setEditingId(pair.id);
    setEditFields({
      selfTerm: pair.self_term ?? "",
      addressTerm: pair.address_term ?? "",
      selfTermChanged: false,
      addressTermChanged: false,
    });
    setHistoryOpenId(null);
    setDeleteConfirmId(null);
    setShowReciprocalForId(null);
  }

  function discardEditPair() {
    setEditingId(null);
    setShowReciprocalForId(null);
  }

  function handleSelfTermChange(val: string, origSelfTerm: string) {
    setEditFields((f) => ({
      ...f,
      selfTerm: val,
      selfTermChanged: val !== origSelfTerm,
    }));
    // Check if both changed → trigger reciprocal
    setShowReciprocalForId(editingId);
  }

  function handleAddressTermChange(val: string, origAddressTerm: string) {
    setEditFields((f) => ({
      ...f,
      addressTerm: val,
      addressTermChanged: val !== origAddressTerm,
    }));
    setShowReciprocalForId(editingId);
  }

  function getReciprocal(
    selfTerm: string,
    addressTerm: string,
  ): { self_term: string; address_term: string } | null {
    const key = `${selfTerm}|${addressTerm}`;
    const rec = pronounsData.kinship_reciprocal[key];
    return rec ?? null;
  }

  const isHardBlocked = (pair: AddressMapDTO) => {
    // CR-04 / D-87: only block if the user is trying to LOCK an unlocked pair with empty terms.
    // Unlocking must always be allowed — D-87 blocks locking-with-empty-term, not unlocking.
    const wouldLock =
      !pair.locked_fields.includes("self_term") &&
      !pair.locked_fields.includes("address_term");
    return (
      wouldLock &&
      (editFields.selfTerm.trim() === "" || editFields.addressTerm.trim() === "")
    );
  };

  async function savePair(pair: AddressMapDTO, lock?: boolean) {
    setSaving(true);
    try {
      const updated = await patchAddressMapPair(seriesId, pair.id, {
        self_term: editFields.selfTerm,
        address_term: editFields.addressTerm,
        ...(lock !== undefined ? { lock } : {}),
      });
      setBible((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          address_map: prev.address_map.map((p) =>
            p.id === pair.id ? updated : p,
          ),
        };
      });
      setEditingId(null);
      setShowReciprocalForId(null);
      showToast({ message: "Pair saved.", variant: "success" });
    } catch {
      showToast({
        message: "Failed to save changes. Check the server logs.",
        variant: "error",
      });
    } finally {
      setSaving(false);
    }
  }

  async function handleConfirmReciprocal(
    pair: AddressMapDTO,
    rec: { self_term: string; address_term: string },
  ) {
    // Save forward pair first
    await savePair(pair);
    // Find reverse pair
    const reversePair = bible.address_map.find(
      (p) =>
        p.speaker_character_id === pair.addressee_character_id &&
        p.addressee_character_id === pair.speaker_character_id,
    );
    if (reversePair) {
      try {
        const updated = await patchAddressMapPair(seriesId, reversePair.id, {
          self_term: rec.self_term,
          address_term: rec.address_term,
        });
        setBible((prev) => {
          if (!prev) return prev;
          return {
            ...prev,
            address_map: prev.address_map.map((p) =>
              p.id === reversePair.id ? updated : p,
            ),
          };
        });
      } catch {
        showToast({
          message:
            "Pair saved, but reverse pair update failed. Set it manually.",
          variant: "error",
        });
        return;
      }
    } else {
      // Try to create reverse pair
      try {
        const newPair = await addAddressMapPair(seriesId, {
          speaker_character_id: pair.addressee_character_id,
          addressee_character_id: pair.speaker_character_id,
          self_term: rec.self_term,
          address_term: rec.address_term,
        });
        setBible((prev) => {
          if (!prev) return prev;
          return {
            ...prev,
            address_map: [...prev.address_map, newPair],
          };
        });
      } catch {
        showToast({
          message:
            "Pair saved, but reverse pair update failed. Set it manually.",
          variant: "error",
        });
      }
    }
    setShowReciprocalForId(null);
  }

  async function handleDeletePair(pairId: number) {
    try {
      await deleteAddressMapPair(seriesId, pairId);
      setBible((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          address_map: prev.address_map.filter((p) => p.id !== pairId),
        };
      });
      setDeleteConfirmId(null);
      showToast({ message: "Pair deleted.", variant: "success" });
    } catch {
      showToast({
        message: "Failed to delete. Check the server logs.",
        variant: "error",
      });
    }
  }

  async function handleAddPair() {
    if (
      !addFields.speaker_character_id ||
      !addFields.addressee_character_id ||
      !addFields.self_term ||
      !addFields.address_term
    )
      return;
    try {
      const newPair = await addAddressMapPair(seriesId, {
        speaker_character_id: Number(addFields.speaker_character_id),
        addressee_character_id: Number(addFields.addressee_character_id),
        self_term: addFields.self_term,
        address_term: addFields.address_term,
      });
      setBible((prev) => {
        if (!prev) return prev;
        return { ...prev, address_map: [...prev.address_map, newPair] };
      });
      setShowAddForm(false);
      setAddFields({
        speaker_character_id: "",
        addressee_character_id: "",
        self_term: "",
        address_term: "",
      });
      showToast({ message: "Pair added.", variant: "success" });
    } catch {
      showToast({
        message: "Failed to save changes. Check the server logs.",
        variant: "error",
      });
    }
  }

  return (
    <SectionCard>
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold text-text-primary">
          Address Map
        </h2>
        <button
          type="button"
          className="text-sm text-accent px-3 py-1 rounded border border-[#3b82f6] hover:bg-[#1e3a5f]"
          onClick={() => setShowAddForm(true)}
        >
          Add Pair
        </button>
      </div>

      {showAddForm && (
        <div className="bg-bg-base border border-[#2d3148] rounded p-3 flex flex-wrap gap-3 items-end">
          <div>
            <label className="text-xs text-text-muted block mb-1">
              Speaker
            </label>
            <select
              value={addFields.speaker_character_id}
              onChange={(e) =>
                setAddFields((f) => ({
                  ...f,
                  speaker_character_id: e.target.value,
                }))
              }
              className="h-9 bg-bg-surface border border-[#2d3148] rounded px-2 text-sm text-text-primary focus:outline-[#3b82f6] focus:outline-2 focus:outline-offset-2"
            >
              <option value="">—</option>
              {bible.characters.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.original_latin_name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-text-muted block mb-1">
              Addressee
            </label>
            <select
              value={addFields.addressee_character_id}
              onChange={(e) =>
                setAddFields((f) => ({
                  ...f,
                  addressee_character_id: e.target.value,
                }))
              }
              className="h-9 bg-bg-surface border border-[#2d3148] rounded px-2 text-sm text-text-primary focus:outline-[#3b82f6] focus:outline-2 focus:outline-offset-2"
            >
              <option value="">—</option>
              {bible.characters.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.original_latin_name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-text-muted block mb-1">
              Self term
            </label>
            <PronounCombo
              value={addFields.self_term}
              onChange={(v) => setAddFields((f) => ({ ...f, self_term: v }))}
              terms={pronounsData.self_terms}
            />
          </div>
          <div>
            <label className="text-xs text-text-muted block mb-1">
              Address term
            </label>
            <PronounCombo
              value={addFields.address_term}
              onChange={(v) =>
                setAddFields((f) => ({ ...f, address_term: v }))
              }
              terms={pronounsData.address_terms}
            />
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              className="text-sm text-accent"
              onClick={handleAddPair}
            >
              Add Pair
            </button>
            <button
              type="button"
              className="text-sm text-text-muted"
              onClick={() => setShowAddForm(false)}
            >
              Discard
            </button>
          </div>
        </div>
      )}

      {bible.address_map.length === 0 ? (
        <p className="text-xs text-text-muted">
          No address pairs. Click Add Pair to add the first one.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-[#2d3148]">
                <th scope="col" className="px-3 py-2 text-left text-xs text-text-muted font-normal" style={{ width: "18%" }}>Speaker</th>
                <th scope="col" className="px-3 py-2 text-left text-xs text-text-muted font-normal" style={{ width: "18%" }}>Addressee</th>
                <th scope="col" className="px-3 py-2 text-left text-xs text-text-muted font-normal" style={{ width: "12%" }}>Self term</th>
                <th scope="col" className="px-3 py-2 text-left text-xs text-text-muted font-normal" style={{ width: "12%" }}>Address term</th>
                <th scope="col" className="px-3 py-2 text-left text-xs text-text-muted font-normal" style={{ width: "10%" }}>Lock</th>
                <th scope="col" className="px-3 py-2 text-left text-xs text-text-muted font-normal" style={{ width: "10%" }}>Events</th>
                <th scope="col" className="px-3 py-2 text-left text-xs text-text-muted font-normal" style={{ width: "10%" }}>From</th>
                <th scope="col" className="px-3 py-2 text-left text-xs text-text-muted font-normal" style={{ width: "5%" }}>History</th>
                <th scope="col" className="px-3 py-2 text-left text-xs text-text-muted font-normal" style={{ width: "5%" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {bible.address_map.map((pair, idx) => {
                const isLocked =
                  pair.locked_fields.includes("self_term") ||
                  pair.locked_fields.includes("address_term");
                const lockState: LockState = isLocked ? "locked" : "inference";
                const isEditing = editingId === pair.id;
                const hardBlocked =
                  isEditing && isHardBlocked(pair);
                const showReciprocal =
                  isEditing &&
                  showReciprocalForId === pair.id &&
                  (editFields.selfTermChanged || editFields.addressTermChanged);

                const reciprocal =
                  isEditing
                    ? getReciprocal(editFields.selfTerm, editFields.addressTerm)
                    : null;

                return (
                  <>
                    <tr
                      key={pair.id}
                      className={[
                        "h-10 border-b border-[#2d3148]",
                        idx % 2 === 1 ? "bg-bg-stripe" : "",
                      ]
                        .filter(Boolean)
                        .join(" ")}
                    >
                      {isEditing ? (
                        <>
                          <td className="px-3 text-sm text-text-primary">
                            {characterName(pair.speaker_character_id)}
                          </td>
                          <td className="px-3 text-sm text-text-primary">
                            {characterName(pair.addressee_character_id)}
                          </td>
                          <td className="px-2">
                            <PronounCombo
                              value={editFields.selfTerm}
                              onChange={(v) =>
                                handleSelfTermChange(v, pair.self_term ?? "")
                              }
                              terms={pronounsData.self_terms}
                            />
                          </td>
                          <td className="px-2">
                            <PronounCombo
                              value={editFields.addressTerm}
                              onChange={(v) =>
                                handleAddressTermChange(
                                  v,
                                  pair.address_term ?? "",
                                )
                              }
                              terms={pronounsData.address_terms}
                            />
                          </td>
                          <td className="px-3">
                            <LockToggleButton
                              state={lockState}
                              onToggle={() =>
                                savePair(pair, !isLocked)
                              }
                              disabled={hardBlocked}
                            />
                          </td>
                          <td className="px-3 text-xs text-text-muted">
                            {bible.relationship_events.filter(
                              (e) =>
                                (e.character_a_id ===
                                  pair.speaker_character_id &&
                                  e.character_b_id ===
                                    pair.addressee_character_id) ||
                                (e.character_b_id ===
                                  pair.speaker_character_id &&
                                  e.character_a_id ===
                                    pair.addressee_character_id),
                            ).length}
                          </td>
                          <td className="px-3 text-xs text-text-muted">
                            {pair.valid_from_episode ?? "—"}
                          </td>
                          <td className="px-3">
                            <button
                              type="button"
                              aria-label="View field history"
                              onClick={() =>
                                setHistoryOpenId(
                                  historyOpenId === pair.id ? null : pair.id,
                                )
                              }
                              className="text-text-muted hover:text-accent"
                            >
                              <Clock size={14} />
                            </button>
                          </td>
                          <td className="px-3 flex items-center gap-1 h-10 flex-wrap">
                            <button
                              type="button"
                              className="text-xs text-accent whitespace-nowrap"
                              disabled={saving}
                              onClick={() => savePair(pair)}
                            >
                              {saving ? "Saving…" : "Save pair"}
                            </button>
                            <button
                              type="button"
                              className="text-xs text-text-muted whitespace-nowrap"
                              onClick={discardEditPair}
                            >
                              Discard changes
                            </button>
                          </td>
                        </>
                      ) : deleteConfirmId === pair.id ? (
                        <>
                          <td
                            colSpan={7}
                            className="px-3 text-xs text-text-primary"
                          >
                            Delete this pair?
                          </td>
                          <td colSpan={2} className="px-3">
                            <div className="flex gap-2">
                              <button
                                type="button"
                                aria-label="Confirm delete"
                                className="text-xs text-[#f87171]"
                                onClick={() => handleDeletePair(pair.id)}
                              >
                                Delete pair
                              </button>
                              <button
                                type="button"
                                className="text-xs text-text-muted"
                                onClick={() => setDeleteConfirmId(null)}
                              >
                                Keep pair
                              </button>
                            </div>
                          </td>
                        </>
                      ) : (
                        <>
                          <td className="px-3 text-sm text-text-primary">
                            {characterName(pair.speaker_character_id)}
                          </td>
                          <td className="px-3 text-sm text-text-primary">
                            {characterName(pair.addressee_character_id)}
                          </td>
                          <td className="px-3 text-xs text-text-primary">
                            {pair.self_term ?? "—"}
                          </td>
                          <td className="px-3 text-xs text-text-primary">
                            {pair.address_term ?? "—"}
                          </td>
                          <td className="px-3">
                            <div className="flex items-center gap-1">
                              <LockBadge state={lockState} />
                              <LockToggleButton
                                state={lockState}
                                onToggle={() => savePair(pair, !isLocked)}
                              />
                            </div>
                          </td>
                          <td className="px-3 text-xs text-text-muted">
                            {bible.relationship_events.filter(
                              (e) =>
                                (e.character_a_id ===
                                  pair.speaker_character_id &&
                                  e.character_b_id ===
                                    pair.addressee_character_id) ||
                                (e.character_b_id ===
                                  pair.speaker_character_id &&
                                  e.character_a_id ===
                                    pair.addressee_character_id),
                            ).length}
                          </td>
                          <td className="px-3 text-xs text-text-muted">
                            {pair.valid_from_episode ?? "—"}
                          </td>
                          <td className="px-3">
                            <button
                              type="button"
                              aria-label="View field history"
                              onClick={() =>
                                setHistoryOpenId(
                                  historyOpenId === pair.id ? null : pair.id,
                                )
                              }
                              className="text-text-muted hover:text-accent"
                            >
                              <Clock size={14} />
                            </button>
                          </td>
                          <td className="px-3">
                            <div className="flex items-center gap-1">
                              <button
                                type="button"
                                aria-label="Edit pair"
                                onClick={() => startEditPair(pair)}
                                className="text-text-muted hover:text-accent"
                              >
                                <Pencil size={14} />
                              </button>
                              {!isLocked && (
                                <button
                                  type="button"
                                  aria-label="Delete pair"
                                  onClick={() => setDeleteConfirmId(pair.id)}
                                  className="text-[#f87171] hover:text-[#ef4444]"
                                >
                                  <Trash2 size={14} />
                                </button>
                              )}
                            </div>
                          </td>
                        </>
                      )}
                    </tr>
                    {/* Hard-block error */}
                    {isEditing && hardBlocked && (
                      <tr key={`${pair.id}-hardblock`}>
                        <td colSpan={9} className="px-3 pb-1">
                          <p
                            role="alert"
                            aria-live="polite"
                            className="text-xs text-[#f87171]"
                          >
                            Both terms must be non-empty before locking a pair.
                          </p>
                        </td>
                      </tr>
                    )}
                    {/* Lock to pin strip (unlocked pair in edit mode) */}
                    {isEditing && !isLocked && !hardBlocked && (
                      <tr key={`${pair.id}-lockstrip`}>
                        <td colSpan={9} className="px-3 pb-1">
                          <div
                            className="text-xs px-2 py-1 rounded"
                            style={{
                              backgroundColor: "#1e3a5f",
                              color: "#60a5fa",
                            }}
                          >
                            This pair is not locked. An upcoming analysis pass
                            may update these terms. Lock to pin your edit
                            permanently.
                          </div>
                        </td>
                      </tr>
                    )}
                    {/* Reciprocal suggestion panel */}
                    {showReciprocal && (
                      <tr key={`${pair.id}-reciprocal`}>
                        <td colSpan={9} className="px-3 pb-2">
                          <ReciprocalSuggestionPanel
                            forwardSelfTerm={editFields.selfTerm}
                            forwardAddressTerm={editFields.addressTerm}
                            reciprocal={reciprocal}
                            onConfirm={(rec) =>
                              handleConfirmReciprocal(pair, rec)
                            }
                            onDismiss={() => setShowReciprocalForId(null)}
                            selfTerms={pronounsData.self_terms}
                            addressTerms={pronounsData.address_terms}
                          />
                        </td>
                      </tr>
                    )}
                    {/* Field history panel */}
                    {historyOpenId === pair.id && (
                      <tr key={`${pair.id}-history`}>
                        <td colSpan={9} className="px-3 pb-2">
                          <FieldHistoryPanel
                            seriesId={seriesId}
                            entityType="address_map"
                            entityId={pair.id}
                            onClose={() => setHistoryOpenId(null)}
                          />
                        </td>
                      </tr>
                    )}
                  </>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </SectionCard>
  );
}

// ── Terms Section ─────────────────────────────────────────────────────────────

interface TermsSectionProps {
  seriesId: number;
  bible: SeriesBibleDTO;
  setBible: React.Dispatch<React.SetStateAction<SeriesBibleDTO | null>>;
  showToast: (t: Omit<ToastState, "id">) => void;
}

function TermsSection({
  seriesId,
  bible,
  setBible,
  showToast,
}: TermsSectionProps) {
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editFields, setEditFields] = useState({
    vietnamese_rendering: "",
    category: "",
  });
  const [historyOpenId, setHistoryOpenId] = useState<number | null>(null);
  const [deleteConfirmId, setDeleteConfirmId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);

  // Add term form
  const [showAddForm, setShowAddForm] = useState(false);
  const [addFields, setAddFields] = useState({
    source_term: "",
    vietnamese_rendering: "",
    category: "",
  });

  function startEdit(term: TermDTO) {
    setEditingId(term.id);
    setEditFields({
      vietnamese_rendering: term.vietnamese_rendering,
      category: term.category ?? "",
    });
    setHistoryOpenId(null);
    setDeleteConfirmId(null);
  }

  function discardEdit() {
    setEditingId(null);
  }

  async function saveTerm(term: TermDTO, lock?: boolean) {
    setSaving(true);
    try {
      const resp = await fetch(
        `/api/series/${seriesId}/terms/${term.id}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            source_term: term.source_term,
            field: "vietnamese_rendering",
            value: editFields.vietnamese_rendering,
            ...(lock !== undefined ? { lock } : {}),
          }),
        },
      );
      if (!resp.ok) throw new Error(`PATCH term: ${resp.status}`);
      const updated: TermDTO = await resp.json();
      // Also patch category if changed
      if (editFields.category !== term.category) {
        const resp2 = await fetch(
          `/api/series/${seriesId}/terms/${term.id}`,
          {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              source_term: term.source_term,
              field: "category",
              value: editFields.category,
            }),
          },
        );
        if (resp2.ok) {
          const updated2: TermDTO = await resp2.json();
          setBible((prev) => {
            if (!prev) return prev;
            return {
              ...prev,
              terms: prev.terms.map((t) => (t.id === term.id ? updated2 : t)),
            };
          });
        }
      } else {
        setBible((prev) => {
          if (!prev) return prev;
          return {
            ...prev,
            terms: prev.terms.map((t) => (t.id === term.id ? updated : t)),
          };
        });
      }
      setEditingId(null);
      showToast({ message: "Term saved.", variant: "success" });
    } catch {
      showToast({
        message: "Failed to save changes. Check the server logs.",
        variant: "error",
      });
    } finally {
      setSaving(false);
    }
  }

  async function toggleTermLock(term: TermDTO) {
    const isLocked = term.locked_fields.length > 0;
    setSaving(true);
    try {
      const resp = await fetch(
        `/api/series/${seriesId}/terms/${term.id}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            source_term: term.source_term,
            field: "vietnamese_rendering",
            value: term.vietnamese_rendering,
            lock: !isLocked,
          }),
        },
      );
      if (!resp.ok) throw new Error(`PATCH term: ${resp.status}`);
      const updated: TermDTO = await resp.json();
      setBible((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          terms: prev.terms.map((t) => (t.id === term.id ? updated : t)),
        };
      });
      showToast({
        message: !isLocked ? "Field locked." : "Field unlocked.",
        variant: "success",
      });
    } catch {
      showToast({
        message: "Failed to save changes. Check the server logs.",
        variant: "error",
      });
    } finally {
      setSaving(false);
    }
  }

  async function handleDeleteTerm(termId: number) {
    try {
      await deleteTerm(seriesId, termId);
      setBible((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          terms: prev.terms.filter((t) => t.id !== termId),
        };
      });
      setDeleteConfirmId(null);
      showToast({ message: "Term deleted.", variant: "success" });
    } catch {
      showToast({
        message: "Failed to delete. Check the server logs.",
        variant: "error",
      });
    }
  }

  async function handleAddTerm() {
    if (!addFields.source_term.trim() || !addFields.vietnamese_rendering.trim())
      return;
    try {
      const newTerm = await addTerm(seriesId, {
        source_term: addFields.source_term.trim(),
        vietnamese_rendering: addFields.vietnamese_rendering.trim(),
        category: addFields.category || undefined,
      });
      setBible((prev) => {
        if (!prev) return prev;
        return { ...prev, terms: [newTerm, ...prev.terms] };
      });
      setShowAddForm(false);
      setAddFields({ source_term: "", vietnamese_rendering: "", category: "" });
      showToast({ message: "Term added.", variant: "success" });
    } catch {
      showToast({
        message: "Failed to save changes. Check the server logs.",
        variant: "error",
      });
    }
  }

  return (
    <SectionCard>
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold text-text-primary">
          Term Dictionary
        </h2>
        <button
          type="button"
          className="text-sm text-accent px-3 py-1 rounded border border-[#3b82f6] hover:bg-[#1e3a5f]"
          onClick={() => setShowAddForm(true)}
        >
          Add Term
        </button>
      </div>
      <p className="text-xs text-text-muted italic -mt-2">
        Source terms are case-sensitive. &apos;Minh&apos; and &apos;minh&apos; are stored separately.
      </p>

      {showAddForm && (
        <div className="bg-bg-base border border-[#2d3148] rounded p-3 flex flex-wrap gap-3 items-end">
          <div>
            <label className="text-xs text-text-muted block mb-1">
              Source term
            </label>
            <input
              type="text"
              autoFocus
              value={addFields.source_term}
              placeholder="e.g. Nguyễn Minh Anh"
              onChange={(e) =>
                setAddFields((f) => ({ ...f, source_term: e.target.value }))
              }
              className="h-9 w-40 bg-bg-surface border border-[#2d3148] rounded px-2 text-sm text-text-primary focus:outline-[#3b82f6] focus:outline-2 focus:outline-offset-2"
            />
          </div>
          <div>
            <label className="text-xs text-text-muted block mb-1">
              Vietnamese rendering
            </label>
            <input
              type="text"
              value={addFields.vietnamese_rendering}
              placeholder="e.g. Minh Anh"
              onChange={(e) =>
                setAddFields((f) => ({
                  ...f,
                  vietnamese_rendering: e.target.value,
                }))
              }
              className="h-9 w-40 bg-bg-surface border border-[#2d3148] rounded px-2 text-sm text-text-primary focus:outline-[#3b82f6] focus:outline-2 focus:outline-offset-2"
            />
          </div>
          <div>
            <label className="text-xs text-text-muted block mb-1">
              Category
            </label>
            <select
              value={addFields.category}
              onChange={(e) =>
                setAddFields((f) => ({ ...f, category: e.target.value }))
              }
              className="h-9 bg-bg-surface border border-[#2d3148] rounded px-2 text-sm text-text-primary focus:outline-[#3b82f6] focus:outline-2 focus:outline-offset-2"
            >
              <option value="">—</option>
              <option value="proper noun">proper noun</option>
              <option value="title">title</option>
              <option value="place">place</option>
              <option value="jargon">jargon</option>
            </select>
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              className="text-sm text-accent"
              onClick={handleAddTerm}
            >
              Add Term
            </button>
            <button
              type="button"
              className="text-sm text-text-muted"
              onClick={() => setShowAddForm(false)}
            >
              Discard
            </button>
          </div>
        </div>
      )}

      {bible.terms.length === 0 ? (
        <p className="text-xs text-text-muted">
          No terms. Click Add Term to add the first one.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-[#2d3148]">
                <th scope="col" className="px-3 py-2 text-left text-xs text-text-muted font-normal" style={{ width: "25%" }}>Source term</th>
                <th scope="col" className="px-3 py-2 text-left text-xs text-text-muted font-normal" style={{ width: "30%" }}>Vietnamese rendering</th>
                <th scope="col" className="px-3 py-2 text-left text-xs text-text-muted font-normal" style={{ width: "15%" }}>Category</th>
                <th scope="col" className="px-3 py-2 text-left text-xs text-text-muted font-normal" style={{ width: "12%" }}>Lock</th>
                <th scope="col" className="px-3 py-2 text-left text-xs text-text-muted font-normal" style={{ width: "8%" }}>History</th>
                <th scope="col" className="px-3 py-2 text-left text-xs text-text-muted font-normal" style={{ width: "10%" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {bible.terms.map((term, idx) => {
                const isLocked = term.locked_fields.length > 0;
                const lockState: LockState = isLocked ? "locked" : "inference";
                const isEditing = editingId === term.id;

                return (
                  <>
                    <tr
                      key={term.id}
                      className={[
                        "h-10 border-b border-[#2d3148]",
                        idx % 2 === 1 ? "bg-bg-stripe" : "",
                      ]
                        .filter(Boolean)
                        .join(" ")}
                    >
                      {isEditing ? (
                        <>
                          <td className="px-3 text-sm text-text-primary">
                            {term.source_term}
                          </td>
                          <td className="px-2">
                            <input
                              type="text"
                              autoFocus
                              value={editFields.vietnamese_rendering}
                              onChange={(e) =>
                                setEditFields((f) => ({
                                  ...f,
                                  vietnamese_rendering: e.target.value,
                                }))
                              }
                              className="h-8 w-full bg-bg-surface border border-[#2d3148] rounded px-1 text-xs text-text-primary focus:outline-[#3b82f6] focus:outline-2 focus:outline-offset-2"
                            />
                          </td>
                          <td className="px-2">
                            <select
                              value={editFields.category}
                              onChange={(e) =>
                                setEditFields((f) => ({
                                  ...f,
                                  category: e.target.value,
                                }))
                              }
                              className="h-8 w-full bg-bg-surface border border-[#2d3148] rounded px-1 text-xs text-text-primary focus:outline-[#3b82f6] focus:outline-2 focus:outline-offset-2"
                            >
                              <option value="">—</option>
                              <option value="proper noun">proper noun</option>
                              <option value="title">title</option>
                              <option value="place">place</option>
                              <option value="jargon">jargon</option>
                            </select>
                          </td>
                          <td className="px-3">
                            <LockToggleButton
                              state={lockState}
                              onToggle={() => toggleTermLock(term)}
                            />
                          </td>
                          <td className="px-3">
                            <button
                              type="button"
                              aria-label="View field history"
                              onClick={() =>
                                setHistoryOpenId(
                                  historyOpenId === term.id ? null : term.id,
                                )
                              }
                              className="text-text-muted hover:text-accent"
                            >
                              <Clock size={14} />
                            </button>
                          </td>
                          <td className="px-3 flex items-center gap-1 h-10">
                            <button
                              type="button"
                              className="text-xs text-accent whitespace-nowrap"
                              disabled={saving}
                              onClick={() => saveTerm(term)}
                            >
                              {saving ? "Saving…" : "Save term"}
                            </button>
                            <button
                              type="button"
                              className="text-xs text-text-muted whitespace-nowrap"
                              onClick={discardEdit}
                            >
                              Discard changes
                            </button>
                          </td>
                        </>
                      ) : deleteConfirmId === term.id ? (
                        <>
                          <td
                            colSpan={4}
                            className="px-3 text-xs text-text-primary"
                          >
                            Delete this term?
                          </td>
                          <td colSpan={2} className="px-3">
                            <div className="flex gap-2">
                              <button
                                type="button"
                                aria-label="Confirm delete"
                                className="text-xs text-[#f87171]"
                                onClick={() => handleDeleteTerm(term.id)}
                              >
                                Delete term
                              </button>
                              <button
                                type="button"
                                className="text-xs text-text-muted"
                                onClick={() => setDeleteConfirmId(null)}
                              >
                                Keep term
                              </button>
                            </div>
                          </td>
                        </>
                      ) : (
                        <>
                          <td className="px-3 text-sm text-text-primary">
                            {term.source_term}
                          </td>
                          <td className="px-3 text-sm text-text-primary">
                            {term.vietnamese_rendering}
                          </td>
                          <td className="px-3 text-xs text-text-muted">
                            {term.category ?? "—"}
                          </td>
                          <td className="px-3">
                            <div className="flex items-center gap-1">
                              <LockBadge state={lockState} />
                              <LockToggleButton
                                state={lockState}
                                onToggle={() => toggleTermLock(term)}
                              />
                            </div>
                          </td>
                          <td className="px-3">
                            <button
                              type="button"
                              aria-label="View field history"
                              onClick={() =>
                                setHistoryOpenId(
                                  historyOpenId === term.id ? null : term.id,
                                )
                              }
                              className="text-text-muted hover:text-accent"
                            >
                              <Clock size={14} />
                            </button>
                          </td>
                          <td className="px-3">
                            <div className="flex items-center gap-1">
                              <button
                                type="button"
                                aria-label="Edit term"
                                onClick={() => startEdit(term)}
                                className="text-text-muted hover:text-accent"
                              >
                                <Pencil size={14} />
                              </button>
                              <button
                                type="button"
                                aria-label="Delete term"
                                onClick={() => setDeleteConfirmId(term.id)}
                                className="text-[#f87171] hover:text-[#ef4444]"
                              >
                                <Trash2 size={14} />
                              </button>
                            </div>
                          </td>
                        </>
                      )}
                    </tr>
                    {historyOpenId === term.id && (
                      <tr key={`${term.id}-history`}>
                        <td colSpan={6} className="px-3 pb-2">
                          <FieldHistoryPanel
                            seriesId={seriesId}
                            entityType="term_dictionary"
                            entityId={term.id}
                            onClose={() => setHistoryOpenId(null)}
                          />
                        </td>
                      </tr>
                    )}
                  </>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </SectionCard>
  );
}

// ── Register Section ──────────────────────────────────────────────────────────

interface RegisterSectionProps {
  seriesId: number;
  bible: SeriesBibleDTO;
  setBible: React.Dispatch<React.SetStateAction<SeriesBibleDTO | null>>;
  showToast: (t: Omit<ToastState, "id">) => void;
}

function RegisterSection({
  seriesId,
  bible,
  setBible,
  showToast,
}: RegisterSectionProps) {
  const [registerValue, setRegisterValue] = useState(bible.register ?? "");
  const [saving, setSaving] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const isLocked = bible.locked_fields.includes("register");
  const lockState: LockState = isLocked ? "locked" : "inference";
  const dirty = registerValue !== (bible.register ?? "");
  const historyRef = useRef<HTMLDivElement>(null);

  async function handleSave() {
    setSaving(true);
    try {
      await patchRegister(seriesId, { value: registerValue, lock: isLocked });
      setBible((prev) => {
        if (!prev) return prev;
        return { ...prev, register: registerValue };
      });
      showToast({ message: "Register saved.", variant: "success" });
    } catch {
      showToast({
        message: "Failed to save changes. Check the server logs.",
        variant: "error",
      });
    } finally {
      setSaving(false);
    }
  }

  async function toggleLock() {
    setSaving(true);
    try {
      await patchRegister(seriesId, {
        value: registerValue,
        lock: !isLocked,
      });
      setBible((prev) => {
        if (!prev) return prev;
        const newLockedFields = !isLocked
          ? [...prev.locked_fields, "register"]
          : prev.locked_fields.filter((f) => f !== "register");
        return { ...prev, locked_fields: newLockedFields };
      });
      showToast({
        message: !isLocked ? "Field locked." : "Field unlocked.",
        variant: "success",
      });
    } catch {
      showToast({
        message: "Failed to save changes. Check the server logs.",
        variant: "error",
      });
    } finally {
      setSaving(false);
    }
  }

  return (
    <SectionCard>
      <h2 className="text-base font-semibold text-text-primary">Register</h2>
      <p className="text-xs text-text-muted -mt-2">
        The register governs formality level across all translation passes.
        Locked register survives re-analysis.
      </p>

      <div className="flex items-end gap-3">
        <div className="flex-1">
          <TextField
            id="register_field"
            label="Register value"
            value={registerValue}
            onChange={setRegisterValue}
            placeholder="e.g. formal, intimate, historical"
          />
        </div>
        <div ref={historyRef} className="flex items-center gap-1 mb-1">
          <LockBadge state={lockState} />
          <LockToggleButton state={lockState} onToggle={toggleLock} />
          <button
            type="button"
            aria-label="View register history"
            onClick={() => setShowHistory((v) => !v)}
            className="text-text-muted hover:text-accent w-8 h-8 flex items-center justify-center"
          >
            <Clock size={14} />
          </button>
        </div>
      </div>

      {!isLocked && (
        <div
          className="text-xs px-3 py-2 rounded"
          style={{ backgroundColor: "#1e3a5f", color: "#60a5fa" }}
        >
          This value may be overwritten on the next episode analysis. Lock to
          pin it.
        </div>
      )}

      {showHistory && (
        <FieldHistoryPanel
          seriesId={seriesId}
          entityType="series"
          entityId={seriesId}
          field="register"
          onClose={() => setShowHistory(false)}
        />
      )}

      <button
        type="button"
        disabled={!dirty || saving}
        onClick={handleSave}
        className="h-9 w-full bg-accent text-white text-sm rounded disabled:opacity-50 hover:bg-[#2563eb] focus:outline-[#3b82f6] focus:outline-2 focus:outline-offset-2 transition-colors duration-150"
      >
        {saving ? "Saving…" : "Save Register"}
      </button>
    </SectionCard>
  );
}
