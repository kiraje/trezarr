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
 * Analog: Settings.tsx (load-on-mount, Card sections, Sonner toast)
 */
import { useState, useEffect, useCallback, useRef, Fragment } from "react";
import { useParams, Link } from "react-router-dom";
import { Clock, Pencil, Trash2 } from "lucide-react";
import { toast } from "sonner";
import {
  getSeriesBible,
  getPronouns,
  getSettings,
  patchCharacter,
  patchAddressMapPair,
  patchRegister,
  patchSeriesOverrides,
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
  type SettingsResponse,
} from "../api/client";
import LockBadge, { type LockState } from "../components/LockBadge";
import LockToggleButton from "../components/LockToggleButton";
import FieldHistoryPanel from "../components/FieldHistoryPanel";
import PronounCombo from "../components/PronounCombo";
import ReciprocalSuggestionPanel from "../components/ReciprocalSuggestionPanel";
import {
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
} from "../components/ui/tabs";
import { Skeleton } from "../components/ui/skeleton";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "../components/ui/card";
import { Input } from "../components/ui/input";
import { Button } from "../components/ui/button";

// ── Helpers ───────────────────────────────────────────────────────────────────

// ShowToast message type — used by section component prop signatures
interface ShowToastArg {
  message: string;
  variant: "success" | "error";
}

function UnreachableBanner({ message }: { message: string }) {
  return (
    <div
      className="w-full mb-4 px-4 py-3 text-sm rounded bg-amber-900/30 border border-amber-800 text-amber-400"
      role="alert"
    >
      {message}
    </div>
  );
}

type Tab = "characters" | "address_map" | "terms" | "register" | "overrides";

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

  const showToast = useCallback((t: ShowToastArg) => {
    if (t.variant === "success") toast.success(t.message);
    else toast.error(t.message);
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
      <div className="flex flex-col gap-2">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-64 w-full" />
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
        <Link to="/bible" className="text-xs text-primary no-underline">
          ← Bible
        </Link>
      </div>
      <div className="flex items-center gap-3 mb-4">
        <h1 className="text-xl font-semibold text-foreground">
          {bible.arr_kind}/{bible.arr_series_id}
        </h1>
        {bible.register && (
          <span className="text-xs text-muted-foreground">{bible.register}</span>
        )}
      </div>

      {unreachable && (
        <UnreachableBanner message="Could not load Bible for this series. Check the server logs." />
      )}

      {/* BibleTabBar — shadcn Tabs primitive */}
      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as Tab)}>
        <TabsList className="mb-4">
          <TabsTrigger value="characters">Characters</TabsTrigger>
          <TabsTrigger value="address_map">Address Map</TabsTrigger>
          <TabsTrigger value="terms">Terms</TabsTrigger>
          <TabsTrigger value="register">Register</TabsTrigger>
          <TabsTrigger value="overrides">Overrides</TabsTrigger>
        </TabsList>
        <TabsContent value="characters">
          <CharactersSection
            seriesId={seriesId}
            bible={bible}
            setBible={setBible}
            showToast={showToast}
          />
        </TabsContent>
        <TabsContent value="address_map">
          <AddressMapSection
            seriesId={seriesId}
            bible={bible}
            setBible={setBible}
            pronounsData={pronounsData}
            showToast={showToast}
          />
        </TabsContent>
        <TabsContent value="terms">
          <TermsSection
            seriesId={seriesId}
            bible={bible}
            setBible={setBible}
            showToast={showToast}
          />
        </TabsContent>
        <TabsContent value="register">
          <RegisterSection
            seriesId={seriesId}
            bible={bible}
            setBible={setBible}
            showToast={showToast}
          />
        </TabsContent>
        <TabsContent value="overrides">
          <OverridesSection
            seriesId={seriesId}
            bible={bible}
            setBible={setBible}
            showToast={showToast}
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}

// ── Characters Section ────────────────────────────────────────────────────────

interface CharactersSectionProps {
  seriesId: number;
  bible: SeriesBibleDTO;
  setBible: React.Dispatch<React.SetStateAction<SeriesBibleDTO | null>>;
  showToast: (t: ShowToastArg) => void;
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
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4">
        <CardTitle>Characters</CardTitle>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => setShowAddForm(true)}
        >
          Add Character
        </Button>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">

      {showAddForm && (
        <div className="border border-border rounded p-3 flex flex-wrap gap-3 items-end">
          <div className="flex-1 min-w-32">
            <label className="text-xs text-muted-foreground block mb-1">
              Name
            </label>
            <Input
              type="text"
              autoFocus
              value={addFields.original_latin_name}
              onChange={(e) =>
                setAddFields((f) => ({
                  ...f,
                  original_latin_name: e.target.value,
                }))
              }
            />
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">
              Gender
            </label>
            <select
              value={addFields.gender}
              onChange={(e) =>
                setAddFields((f) => ({ ...f, gender: e.target.value }))
              }
              className="h-9 rounded-md border border-border bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <option value="">—</option>
              <option value="male">male</option>
              <option value="female">female</option>
              <option value="unknown">unknown</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">
              Age
            </label>
            <Input
              type="text"
              value={addFields.rough_age}
              onChange={(e) =>
                setAddFields((f) => ({ ...f, rough_age: e.target.value }))
              }
              className="w-20"
            />
          </div>
          <div className="flex-1 min-w-32">
            <label className="text-xs text-muted-foreground block mb-1">
              Role
            </label>
            <Input
              type="text"
              value={addFields.role}
              onChange={(e) =>
                setAddFields((f) => ({ ...f, role: e.target.value }))
              }
            />
          </div>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="default"
              size="sm"
              onClick={handleAddCharacter}
            >
              Add Character
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => setShowAddForm(false)}
            >
              Discard
            </Button>
          </div>
        </div>
      )}

      {bible.characters.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          No characters. Click Add Character to add the first one.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border">
                <th
                  scope="col"
                  className="px-3 py-2 text-left text-xs text-muted-foreground font-normal"
                  style={{ width: "22%" }}
                >
                  Name
                </th>
                <th
                  scope="col"
                  className="px-3 py-2 text-left text-xs text-muted-foreground font-normal"
                  style={{ width: "12%" }}
                >
                  Gender
                </th>
                <th
                  scope="col"
                  className="px-3 py-2 text-left text-xs text-muted-foreground font-normal"
                  style={{ width: "10%" }}
                >
                  Age
                </th>
                <th
                  scope="col"
                  className="px-3 py-2 text-left text-xs text-muted-foreground font-normal"
                  style={{ width: "28%" }}
                >
                  Role
                </th>
                <th
                  scope="col"
                  className="px-3 py-2 text-left text-xs text-muted-foreground font-normal"
                  style={{ width: "14%" }}
                >
                  Lock
                </th>
                <th
                  scope="col"
                  className="px-3 py-2 text-left text-xs text-muted-foreground font-normal"
                  style={{ width: "7%" }}
                >
                  History
                </th>
                <th
                  scope="col"
                  className="px-3 py-2 text-left text-xs text-muted-foreground font-normal"
                  style={{ width: "7%" }}
                >
                  Actions
                </th>
              </tr>
            </thead>
            <tbody>
              {bible.characters.map((char) => (
                <Fragment key={char.id}>
                  <tr
                    className="h-10 border-b border-border"
                  >
                    {editingId === char.id ? (
                      <>
                        <td className="px-3 text-sm text-foreground">
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
                            className="h-8 w-full rounded-md border border-border bg-background px-1 text-xs text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                          >
                            <option value="">—</option>
                            <option value="male">male</option>
                            <option value="female">female</option>
                            <option value="unknown">unknown</option>
                          </select>
                        </td>
                        <td className="px-2">
                          <Input
                            type="text"
                            value={editFields.rough_age}
                            onChange={(e) =>
                              setEditFields((f) => ({
                                ...f,
                                rough_age: e.target.value,
                              }))
                            }
                            className="h-8 text-xs"
                          />
                        </td>
                        <td className="px-2">
                          <Input
                            type="text"
                            value={editFields.role}
                            onChange={(e) =>
                              setEditFields((f) => ({
                                ...f,
                                role: e.target.value,
                              }))
                            }
                            className="h-8 text-xs"
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
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            aria-label="View field history"
                            onClick={() =>
                              setHistoryOpenId(
                                historyOpenId === char.id ? null : char.id,
                              )
                            }
                          >
                            <Clock size={14} />
                          </Button>
                        </td>
                        <td className="px-3 flex items-center gap-2 h-10">
                          <Button
                            type="button"
                            variant="default"
                            size="sm"
                            disabled={saving}
                            onClick={() => saveCharacter(char)}
                          >
                            {saving ? "Saving…" : "Save"}
                          </Button>
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            onClick={discardEdit}
                          >
                            Discard
                          </Button>
                        </td>
                      </>
                    ) : (
                      <>
                        <td className="px-3 text-sm text-foreground">
                          {char.original_latin_name}
                        </td>
                        <td className="px-3 text-xs text-foreground">
                          {char.gender ?? "—"}
                        </td>
                        <td className="px-3 text-xs text-foreground">
                          {char.rough_age ?? "—"}
                        </td>
                        <td className="px-3 text-xs text-foreground">
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
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            aria-label="View field history"
                            onClick={() =>
                              setHistoryOpenId(
                                historyOpenId === char.id ? null : char.id,
                              )
                            }
                          >
                            <Clock size={14} />
                          </Button>
                        </td>
                        <td className="px-3">
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            aria-label="Edit character"
                            onClick={() => startEdit(char)}
                          >
                            <Pencil size={14} />
                          </Button>
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
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
      </CardContent>
    </Card>
  );
}

// ── Address Map Section ───────────────────────────────────────────────────────

interface AddressMapSectionProps {
  seriesId: number;
  bible: SeriesBibleDTO;
  setBible: React.Dispatch<React.SetStateAction<SeriesBibleDTO | null>>;
  pronounsData: PronounsResponse;
  showToast: (t: ShowToastArg) => void;
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

  // Private helper — patches the pair in state but does NOT fire a toast or
  // reset editingId. Used by handleConfirmReciprocal so the composite operation
  // can issue a single success/failure toast after both writes settle.
  async function savePairCore(pair: AddressMapDTO, lock?: boolean): Promise<void> {
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
  }

  async function savePair(pair: AddressMapDTO, lock?: boolean) {
    setSaving(true);
    try {
      await savePairCore(pair, lock);
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
    setSaving(true);
    try {
      // Save forward pair (no toast, no row close yet)
      await savePairCore(pair);

      // Save or create the reverse pair
      const reversePair = bible.address_map.find(
        (p) =>
          p.speaker_character_id === pair.addressee_character_id &&
          p.addressee_character_id === pair.speaker_character_id,
      );
      if (reversePair) {
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
      } else {
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
      }

      // Both writes succeeded — close the row and show a single success toast
      setEditingId(null);
      setShowReciprocalForId(null);
      showToast({ message: "Both pairs saved.", variant: "success" });
    } catch {
      // Either write failed — do NOT close the row, do NOT show success
      showToast({
        message: "Failed to save changes. Check the server logs.",
        variant: "error",
      });
    } finally {
      setSaving(false);
    }
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
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4">
        <CardTitle>Address Map</CardTitle>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => setShowAddForm(true)}
        >
          Add Pair
        </Button>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">

      {showAddForm && (
        <div className="border border-border rounded p-3 flex flex-wrap gap-3 items-end">
          <div>
            <label className="text-xs text-muted-foreground block mb-1">
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
              className="h-9 rounded-md border border-border bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
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
            <label className="text-xs text-muted-foreground block mb-1">
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
              className="h-9 rounded-md border border-border bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
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
            <label className="text-xs text-muted-foreground block mb-1">
              Self term
            </label>
            <PronounCombo
              value={addFields.self_term}
              onChange={(v) => setAddFields((f) => ({ ...f, self_term: v }))}
              terms={pronounsData.self_terms}
            />
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">
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
            <Button
              type="button"
              variant="default"
              size="sm"
              onClick={handleAddPair}
            >
              Add Pair
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => setShowAddForm(false)}
            >
              Discard
            </Button>
          </div>
        </div>
      )}

      {bible.address_map.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          No address pairs. Click Add Pair to add the first one.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border">
                <th scope="col" className="px-3 py-2 text-left text-xs text-muted-foreground font-normal" style={{ width: "18%" }}>Speaker</th>
                <th scope="col" className="px-3 py-2 text-left text-xs text-muted-foreground font-normal" style={{ width: "18%" }}>Addressee</th>
                <th scope="col" className="px-3 py-2 text-left text-xs text-muted-foreground font-normal" style={{ width: "12%" }}>Self term</th>
                <th scope="col" className="px-3 py-2 text-left text-xs text-muted-foreground font-normal" style={{ width: "12%" }}>Address term</th>
                <th scope="col" className="px-3 py-2 text-left text-xs text-muted-foreground font-normal" style={{ width: "10%" }}>Lock</th>
                <th scope="col" className="px-3 py-2 text-left text-xs text-muted-foreground font-normal" style={{ width: "10%" }}>Events</th>
                <th scope="col" className="px-3 py-2 text-left text-xs text-muted-foreground font-normal" style={{ width: "10%" }}>From</th>
                <th scope="col" className="px-3 py-2 text-left text-xs text-muted-foreground font-normal" style={{ width: "5%" }}>History</th>
                <th scope="col" className="px-3 py-2 text-left text-xs text-muted-foreground font-normal" style={{ width: "5%" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {bible.address_map.map((pair) => {
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
                  <Fragment key={pair.id}>
                    <tr
                      className="h-10 border-b border-border"
                    >
                      {isEditing ? (
                        <>
                          <td className="px-3 text-sm text-foreground">
                            {characterName(pair.speaker_character_id)}
                          </td>
                          <td className="px-3 text-sm text-foreground">
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
                          <td className="px-3 text-xs text-muted-foreground">
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
                          <td className="px-3 text-xs text-muted-foreground">
                            {pair.valid_from_episode ?? "—"}
                          </td>
                          <td className="px-3">
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon"
                              aria-label="View field history"
                              onClick={() =>
                                setHistoryOpenId(
                                  historyOpenId === pair.id ? null : pair.id,
                                )
                              }
                            >
                              <Clock size={14} />
                            </Button>
                          </td>
                          <td className="px-3 flex items-center gap-1 h-10 flex-wrap">
                            <Button
                              type="button"
                              variant="default"
                              size="sm"
                              disabled={saving}
                              onClick={() => savePair(pair)}
                            >
                              {saving ? "Saving…" : "Save"}
                            </Button>
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              onClick={discardEditPair}
                            >
                              Discard
                            </Button>
                          </td>
                        </>
                      ) : deleteConfirmId === pair.id ? (
                        <>
                          <td
                            colSpan={7}
                            className="px-3 text-xs text-foreground"
                          >
                            Delete this pair?
                          </td>
                          <td colSpan={2} className="px-3">
                            <div className="flex gap-2">
                              <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                aria-label="Confirm delete"
                                className="text-destructive hover:text-destructive"
                                onClick={() => handleDeletePair(pair.id)}
                              >
                                Delete pair
                              </Button>
                              <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                onClick={() => setDeleteConfirmId(null)}
                              >
                                Keep pair
                              </Button>
                            </div>
                          </td>
                        </>
                      ) : (
                        <>
                          <td className="px-3 text-sm text-foreground">
                            {characterName(pair.speaker_character_id)}
                          </td>
                          <td className="px-3 text-sm text-foreground">
                            {characterName(pair.addressee_character_id)}
                          </td>
                          <td className="px-3 text-xs text-foreground">
                            {pair.self_term ?? "—"}
                          </td>
                          <td className="px-3 text-xs text-foreground">
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
                          <td className="px-3 text-xs text-muted-foreground">
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
                          <td className="px-3 text-xs text-muted-foreground">
                            {pair.valid_from_episode ?? "—"}
                          </td>
                          <td className="px-3">
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon"
                              aria-label="View field history"
                              onClick={() =>
                                setHistoryOpenId(
                                  historyOpenId === pair.id ? null : pair.id,
                                )
                              }
                            >
                              <Clock size={14} />
                            </Button>
                          </td>
                          <td className="px-3">
                            <div className="flex items-center gap-1">
                              <Button
                                type="button"
                                variant="ghost"
                                size="icon"
                                aria-label="Edit pair"
                                onClick={() => startEditPair(pair)}
                              >
                                <Pencil size={14} />
                              </Button>
                              {!isLocked && (
                                <Button
                                  type="button"
                                  variant="ghost"
                                  size="icon"
                                  aria-label="Delete pair"
                                  className="text-destructive hover:text-destructive"
                                  onClick={() => setDeleteConfirmId(pair.id)}
                                >
                                  <Trash2 size={14} />
                                </Button>
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
                            className="text-xs text-destructive"
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
                          <div className="text-xs px-2 py-1 rounded bg-primary/15 text-primary">
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
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      </CardContent>
    </Card>
  );
}

// ── Terms Section ─────────────────────────────────────────────────────────────

interface TermsSectionProps {
  seriesId: number;
  bible: SeriesBibleDTO;
  setBible: React.Dispatch<React.SetStateAction<SeriesBibleDTO | null>>;
  showToast: (t: ShowToastArg) => void;
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
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle>Term Dictionary</CardTitle>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => setShowAddForm(true)}
        >
          Add Term
        </Button>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
      <p className="text-xs text-muted-foreground italic">
        Source terms are case-sensitive. &apos;Minh&apos; and &apos;minh&apos; are stored separately.
      </p>

      {showAddForm && (
        <div className="border border-border rounded p-3 flex flex-wrap gap-3 items-end">
          <div>
            <label className="text-xs text-muted-foreground block mb-1">
              Source term
            </label>
            <Input
              type="text"
              autoFocus
              value={addFields.source_term}
              placeholder="e.g. Nguyễn Minh Anh"
              onChange={(e) =>
                setAddFields((f) => ({ ...f, source_term: e.target.value }))
              }
              className="w-40"
            />
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">
              Vietnamese rendering
            </label>
            <Input
              type="text"
              value={addFields.vietnamese_rendering}
              placeholder="e.g. Minh Anh"
              onChange={(e) =>
                setAddFields((f) => ({
                  ...f,
                  vietnamese_rendering: e.target.value,
                }))
              }
              className="w-40"
            />
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">
              Category
            </label>
            <select
              value={addFields.category}
              onChange={(e) =>
                setAddFields((f) => ({ ...f, category: e.target.value }))
              }
              className="h-9 rounded-md border border-border bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <option value="">—</option>
              <option value="proper noun">proper noun</option>
              <option value="title">title</option>
              <option value="place">place</option>
              <option value="jargon">jargon</option>
            </select>
          </div>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="default"
              size="sm"
              onClick={handleAddTerm}
            >
              Add Term
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => setShowAddForm(false)}
            >
              Discard
            </Button>
          </div>
        </div>
      )}

      {bible.terms.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          No terms. Click Add Term to add the first one.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border">
                <th scope="col" className="px-3 py-2 text-left text-xs text-muted-foreground font-normal" style={{ width: "25%" }}>Source term</th>
                <th scope="col" className="px-3 py-2 text-left text-xs text-muted-foreground font-normal" style={{ width: "30%" }}>Vietnamese rendering</th>
                <th scope="col" className="px-3 py-2 text-left text-xs text-muted-foreground font-normal" style={{ width: "15%" }}>Category</th>
                <th scope="col" className="px-3 py-2 text-left text-xs text-muted-foreground font-normal" style={{ width: "12%" }}>Lock</th>
                <th scope="col" className="px-3 py-2 text-left text-xs text-muted-foreground font-normal" style={{ width: "8%" }}>History</th>
                <th scope="col" className="px-3 py-2 text-left text-xs text-muted-foreground font-normal" style={{ width: "10%" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {bible.terms.map((term) => {
                const isLocked = term.locked_fields.length > 0;
                const lockState: LockState = isLocked ? "locked" : "inference";
                const isEditing = editingId === term.id;

                return (
                  <Fragment key={term.id}>
                    <tr
                      className="h-10 border-b border-border"
                    >
                      {isEditing ? (
                        <>
                          <td className="px-3 text-sm text-foreground">
                            {term.source_term}
                          </td>
                          <td className="px-2">
                            <Input
                              type="text"
                              autoFocus
                              value={editFields.vietnamese_rendering}
                              onChange={(e) =>
                                setEditFields((f) => ({
                                  ...f,
                                  vietnamese_rendering: e.target.value,
                                }))
                              }
                              className="h-8 text-xs"
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
                              className="h-8 w-full rounded-md border border-border bg-background px-1 text-xs text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
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
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon"
                              aria-label="View field history"
                              onClick={() =>
                                setHistoryOpenId(
                                  historyOpenId === term.id ? null : term.id,
                                )
                              }
                            >
                              <Clock size={14} />
                            </Button>
                          </td>
                          <td className="px-3 flex items-center gap-1 h-10">
                            <Button
                              type="button"
                              variant="default"
                              size="sm"
                              disabled={saving}
                              onClick={() => saveTerm(term)}
                            >
                              {saving ? "Saving…" : "Save"}
                            </Button>
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              onClick={discardEdit}
                            >
                              Discard
                            </Button>
                          </td>
                        </>
                      ) : deleteConfirmId === term.id ? (
                        <>
                          <td
                            colSpan={4}
                            className="px-3 text-xs text-foreground"
                          >
                            Delete this term?
                          </td>
                          <td colSpan={2} className="px-3">
                            <div className="flex gap-2">
                              <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                aria-label="Confirm delete"
                                className="text-destructive hover:text-destructive"
                                onClick={() => handleDeleteTerm(term.id)}
                              >
                                Delete term
                              </Button>
                              <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                onClick={() => setDeleteConfirmId(null)}
                              >
                                Keep term
                              </Button>
                            </div>
                          </td>
                        </>
                      ) : (
                        <>
                          <td className="px-3 text-sm text-foreground">
                            {term.source_term}
                          </td>
                          <td className="px-3 text-sm text-foreground">
                            {term.vietnamese_rendering}
                          </td>
                          <td className="px-3 text-xs text-muted-foreground">
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
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon"
                              aria-label="View field history"
                              onClick={() =>
                                setHistoryOpenId(
                                  historyOpenId === term.id ? null : term.id,
                                )
                              }
                            >
                              <Clock size={14} />
                            </Button>
                          </td>
                          <td className="px-3">
                            <div className="flex items-center gap-1">
                              <Button
                                type="button"
                                variant="ghost"
                                size="icon"
                                aria-label="Edit term"
                                onClick={() => startEdit(term)}
                              >
                                <Pencil size={14} />
                              </Button>
                              <Button
                                type="button"
                                variant="ghost"
                                size="icon"
                                aria-label="Delete term"
                                className="text-destructive hover:text-destructive"
                                onClick={() => setDeleteConfirmId(term.id)}
                              >
                                <Trash2 size={14} />
                              </Button>
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
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      </CardContent>
    </Card>
  );
}

// ── Register Section ──────────────────────────────────────────────────────────

interface RegisterSectionProps {
  seriesId: number;
  bible: SeriesBibleDTO;
  setBible: React.Dispatch<React.SetStateAction<SeriesBibleDTO | null>>;
  showToast: (t: ShowToastArg) => void;
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
    <Card>
      <CardHeader className="pb-2">
        <CardTitle>Register</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
      <p className="text-xs text-muted-foreground">
        The register governs formality level across all translation passes.
        Locked register survives re-analysis.
      </p>

      <div className="flex items-end gap-3">
        <div className="flex-1">
          <label htmlFor="register_field" className="text-xs text-muted-foreground block mb-1">
            Register value
          </label>
          <Input
            id="register_field"
            type="text"
            value={registerValue}
            onChange={(e) => setRegisterValue(e.target.value)}
            placeholder="e.g. formal, intimate, historical"
          />
        </div>
        <div ref={historyRef} className="flex items-center gap-1 mb-1">
          <LockBadge state={lockState} />
          <LockToggleButton state={lockState} onToggle={toggleLock} />
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label="View register history"
            onClick={() => setShowHistory((v) => !v)}
          >
            <Clock size={14} />
          </Button>
        </div>
      </div>

      {!isLocked && (
        <div className="text-xs px-3 py-2 rounded bg-primary/15 text-primary">
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

      <Button
        type="button"
        variant="default"
        className="w-full"
        disabled={!dirty || saving}
        onClick={handleSave}
      >
        {saving ? "Saving…" : "Save Register"}
      </Button>
      </CardContent>
    </Card>
  );
}

// ── Source Priority Editor ────────────────────────────────────────────────────

interface SourcePriorityEditorProps {
  value: string[];
  globalDefault: string[];
  onChange: (v: string[] | null) => void;
  onClear?: () => void;
  disabled?: boolean;
}

function SourcePriorityEditor({
  value,
  globalDefault,
  onChange,
  onClear,
  disabled = false,
}: SourcePriorityEditorProps) {
  const [inputValue, setInputValue] = useState("");
  const [inputError, setInputError] = useState<string | null>(null);

  function handleRemove(code: string) {
    const next = value.filter((c) => c !== code);
    onChange(next.length > 0 ? next : null);
  }

  function commitInput(raw: string) {
    const trimmed = raw.trim().toLowerCase();
    if (!trimmed) {
      setInputError(null);
      return;
    }
    if (!/^[a-z]{2}$/.test(trimmed)) {
      setInputError("Must be a 2-letter ISO-639-1 code (e.g. ko, zh, en)");
      return;
    }
    setInputError(null);
    if (!value.includes(trimmed)) {
      const next = [...value, trimmed];
      onChange(next);
    }
    setInputValue("");
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      e.preventDefault();
      commitInput(inputValue);
    }
  }

  function handleBlur() {
    commitInput(inputValue);
  }

  const isOverridden = value.length > 0;

  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs text-muted-foreground">Source language preference</span>
      {isOverridden ? (
        <span className="text-xs text-primary">Per-series override active</span>
      ) : (
        <span className="text-xs text-muted-foreground">
          Inherited from global config:{" "}
          {globalDefault.length > 0 ? globalDefault.join(", ") : "—"}
        </span>
      )}
      <div className="flex flex-wrap items-center gap-2 min-h-[28px]">
        {value.map((code) => (
          <span
            key={code}
            className="flex items-center h-7 px-2 gap-2 bg-card text-xs text-foreground border border-border rounded"
          >
            {code}
            <button
              type="button"
              aria-label={`Remove ${code} from source priority`}
              disabled={disabled}
              onClick={() => handleRemove(code)}
              className="text-muted-foreground hover:text-destructive focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60 disabled:cursor-not-allowed"
            >
              ×
            </button>
          </span>
        ))}
        <Input
          type="text"
          placeholder="+ Add"
          aria-label="Add language code"
          value={inputValue}
          disabled={disabled}
          onChange={(e) => {
            setInputValue(e.target.value);
            setInputError(null);
          }}
          onKeyDown={handleKeyDown}
          onBlur={handleBlur}
          className="h-7 w-16 text-xs"
        />
      </div>
      {inputError && (
        <p role="alert" className="text-xs text-destructive">
          {inputError}
        </p>
      )}
      {isOverridden && (
        <button
          type="button"
          disabled={disabled}
          onClick={() => (onClear ? onClear() : onChange(null))}
          className="text-xs text-primary self-start focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60 disabled:cursor-not-allowed"
        >
          Clear source override
        </button>
      )}
    </div>
  );
}

// ── Overrides Section ─────────────────────────────────────────────────────────

interface OverridesSectionProps {
  seriesId: number;
  bible: SeriesBibleDTO;
  setBible: React.Dispatch<React.SetStateAction<SeriesBibleDTO | null>>;
  showToast: (t: ShowToastArg) => void;
}

function OverridesSection({
  seriesId,
  bible,
  setBible,
  showToast,
}: OverridesSectionProps) {
  const [sourcePriority, setSourcePriority] = useState<string[]>(
    bible.source_lang_override ?? [],
  );
  const [modelValue, setModelValue] = useState(bible.model_override ?? "");
  const [modelError, setModelError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [globalSettings, setGlobalSettings] =
    useState<SettingsResponse | null>(null);

  // Register sub-section state (independent of overrides save path)
  const [registerValue, setRegisterValue] = useState(bible.register ?? "");
  const [registerSaving, setRegisterSaving] = useState(false);
  const isRegisterLocked = bible.locked_fields.includes("register");
  const registerLockState: LockState = isRegisterLocked ? "locked" : "inference";
  const registerDirty = registerValue !== (bible.register ?? "");

  useEffect(() => {
    getSettings()
      .then(setGlobalSettings)
      .catch(() => {
        /* degrade gracefully — provenance badges show fallback text */
      });
  }, []);

  const dirty =
    JSON.stringify(sourcePriority) !==
      JSON.stringify(bible.source_lang_override ?? []) ||
    modelValue !== (bible.model_override ?? "");

  const globalSourceDefault = Array.isArray(
    globalSettings?.source_lang_priority,
  )
    ? (globalSettings.source_lang_priority as string[])
    : [];
  const globalModel =
    typeof globalSettings?.llm_model === "string"
      ? globalSettings.llm_model
      : "";

  async function handleSave() {
    // Validate model length (T-10-11)
    if (modelValue.length > 256) {
      setModelError("Model ID must be 256 characters or fewer");
      return;
    }
    setModelError(null);
    setSaving(true);
    try {
      // CRITICAL (D-111): only source_lang_override and model_override — register excluded
      const updated = await patchSeriesOverrides(seriesId, {
        source_lang_override:
          sourcePriority.length > 0 ? sourcePriority : null,
        model_override: modelValue.trim() || null,
      });
      setBible((prev) =>
        prev
          ? {
              ...prev,
              source_lang_override: updated.source_lang_override,
              model_override: updated.model_override,
            }
          : prev,
      );
      showToast({ message: "Overrides saved.", variant: "success" });
    } catch {
      showToast({
        message: "Failed to save overrides. Check the server logs.",
        variant: "error",
      });
    } finally {
      setSaving(false);
    }
  }

  async function handleClearSource() {
    setSaving(true);
    try {
      const updated = await patchSeriesOverrides(seriesId, {
        source_lang_override: null,
        model_override: modelValue.trim() || null,
      });
      setSourcePriority([]);
      setBible((prev) =>
        prev
          ? {
              ...prev,
              source_lang_override: updated.source_lang_override,
              model_override: updated.model_override,
            }
          : prev,
      );
      showToast({ message: "Overrides saved.", variant: "success" });
    } catch {
      showToast({
        message: "Failed to save overrides. Check the server logs.",
        variant: "error",
      });
    } finally {
      setSaving(false);
    }
  }

  async function handleClearModel() {
    setSaving(true);
    try {
      const updated = await patchSeriesOverrides(seriesId, {
        source_lang_override:
          sourcePriority.length > 0 ? sourcePriority : null,
        model_override: null,
      });
      setModelValue("");
      setModelError(null);
      setBible((prev) =>
        prev
          ? {
              ...prev,
              source_lang_override: updated.source_lang_override,
              model_override: updated.model_override,
            }
          : prev,
      );
      showToast({ message: "Overrides saved.", variant: "success" });
    } catch {
      showToast({
        message: "Failed to save overrides. Check the server logs.",
        variant: "error",
      });
    } finally {
      setSaving(false);
    }
  }

  // Register sub-section: independent save path via patchRegister (NOT patchSeriesOverrides)
  async function handleSaveRegister() {
    setRegisterSaving(true);
    try {
      await patchRegister(seriesId, {
        value: registerValue,
        lock: isRegisterLocked,
      });
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
      setRegisterSaving(false);
    }
  }

  async function toggleRegisterLock() {
    setRegisterSaving(true);
    try {
      await patchRegister(seriesId, {
        value: registerValue,
        lock: !isRegisterLocked,
      });
      setBible((prev) => {
        if (!prev) return prev;
        const newLockedFields = !isRegisterLocked
          ? [...prev.locked_fields, "register"]
          : prev.locked_fields.filter((f) => f !== "register");
        return { ...prev, locked_fields: newLockedFields };
      });
      showToast({
        message: !isRegisterLocked ? "Field locked." : "Field unlocked.",
        variant: "success",
      });
    } catch {
      showToast({
        message: "Failed to save changes. Check the server logs.",
        variant: "error",
      });
    } finally {
      setRegisterSaving(false);
    }
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle>Overrides</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
      <p className="text-xs text-muted-foreground">
        Per-series overrides take priority over global config. Leave blank to
        inherit the global default.
      </p>

      {/* Source Language Preference */}
      <SourcePriorityEditor
        value={sourcePriority}
        globalDefault={globalSourceDefault}
        onChange={(v) => setSourcePriority(v ?? [])}
        onClear={handleClearSource}
        disabled={saving}
      />

      {/* Model Override */}
      <div className="flex flex-col gap-1">
        <span className="text-xs text-muted-foreground">Model override</span>
        {modelValue.trim() ? (
          <span className="text-xs text-primary">Per-series override active</span>
        ) : (
          <span className="text-xs text-muted-foreground">
            Inherited: {globalModel || "—"}
          </span>
        )}
        <Input
          id="model_override"
          type="text"
          value={modelValue}
          onChange={(e) => {
            setModelValue(e.target.value);
            if (e.target.value.length <= 256) setModelError(null);
          }}
          placeholder={globalModel || "e.g. gpt-4o"}
          disabled={saving}
          maxLength={300}
        />
        {modelError && (
          <p role="alert" className="text-xs text-destructive">
            {modelError}
          </p>
        )}
        {modelValue.trim() && (
          <button
            type="button"
            disabled={saving}
            onClick={handleClearModel}
            className="text-xs text-primary self-start focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60 disabled:cursor-not-allowed"
          >
            Clear model override
          </button>
        )}
      </div>

      {/* Register sub-section — independent save path via patchRegister (NOT patchSeriesOverrides) */}
      <div className="flex flex-col gap-1 pt-2 border-t border-border">
        <div className="flex items-end gap-3">
          <div className="flex-1">
            <label htmlFor="register_override" className="text-xs text-muted-foreground block mb-1">
              Register
            </label>
            <Input
              id="register_override"
              type="text"
              value={registerValue}
              onChange={(e) => setRegisterValue(e.target.value)}
              placeholder="e.g. formal, intimate, historical"
              disabled={registerSaving}
            />
          </div>
          <div className="flex items-center gap-1 mb-1">
            <LockBadge state={registerLockState} />
            <LockToggleButton
              state={registerLockState}
              onToggle={toggleRegisterLock}
            />
          </div>
        </div>
        {!isRegisterLocked && (
          <div className="text-xs px-3 py-2 rounded bg-primary/15 text-primary">
            This value may be overwritten on the next episode analysis. Lock to
            pin it.
          </div>
        )}
        <Button
          type="button"
          variant="default"
          className="w-full"
          disabled={!registerDirty || registerSaving}
          onClick={handleSaveRegister}
        >
          {registerSaving ? "Saving…" : "Save Register"}
        </Button>
      </div>

      {/* Save Overrides button — controls source_lang_override + model_override ONLY (D-111) */}
      <Button
        type="button"
        variant="default"
        className="w-full"
        disabled={!dirty || saving}
        onClick={handleSave}
      >
        {saving ? "Saving…" : "Save Overrides"}
      </Button>
      </CardContent>
    </Card>
  );
}
