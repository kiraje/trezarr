/**
 * Settings page — configuration for all services (SVC-02).
 *
 * Conforms to 07-UI-SPEC.md §Settings View:
 * - 6 connection sections in card layout (bg-surface, rounded, border)
 * - Two-column grid on wide viewports, single column below 768px
 * - Labels above inputs; MaskedSecretInput for API keys
 * - Save button per section (disabled when no unsaved changes)
 * - env-locked fields rendered as disabled MaskedSecretInput
 * - Restart-required banner after save
 * - ConnectionTestButton for Sonarr, Radarr, Bazarr, LLM
 * - Copywriting contract: "Save Settings", "Test Connection", etc.
 */
import { useState, useEffect, useCallback } from "react";
import {
  getSettings,
  putSettings,
  getEnvLocked,
  type SettingsResponse,
} from "../api/client";
import MaskedSecretInput from "../components/MaskedSecretInput";
import ConnectionTestButton from "../components/ConnectionTestButton";
import Toast from "../components/Toast";
import type { ToastState } from "../components/Toast";

// ── Unreachable banner ────────────────────────────────────────────────────────

function UnreachableBanner() {
  return (
    <div
      className="w-full mb-4 px-4 py-3 text-sm rounded"
      style={{ backgroundColor: "#451a03", color: "#fbbf24" }}
      role="alert"
    >
      Cannot reach the Trezarr service. Check that the server is running.
    </div>
  );
}

// ── Section card ─────────────────────────────────────────────────────────────

function SectionCard({ children }: { children: React.ReactNode }) {
  return (
    <div className="bg-bg-surface border border-[#2d3148] rounded p-6 flex flex-col gap-4">
      {children}
    </div>
  );
}

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="text-lg font-semibold text-[#e2e6f0] leading-tight">
      {children}
    </h2>
  );
}

function FieldGrid({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">{children}</div>
  );
}

interface TextFieldProps {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  disabled?: boolean;
}

function TextField({
  id,
  label,
  value,
  onChange,
  type = "text",
  disabled = false,
}: TextFieldProps) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-xs text-[#6b7280]">
        {label}
      </label>
      <input
        id={id}
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        className="h-9 w-full bg-bg-surface border border-[#2d3148] rounded px-2 text-sm text-[#e2e6f0] focus:outline-[#3b82f6] focus:outline-2 focus:outline-offset-2 disabled:opacity-60 disabled:cursor-not-allowed"
      />
    </div>
  );
}

function RestartBanner() {
  return (
    <div
      className="flex items-center gap-2 text-sm"
      style={{ color: "#fbbf24" }}
      role="status"
    >
      Some changes require a service restart to take effect.
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function Settings() {
  const [settings, setSettings] = useState<SettingsResponse | null>(null);
  const [envLocked, setEnvLocked] = useState<string[]>([]);
  const [unreachable, setUnreachable] = useState(false);
  const [toast, setToast] = useState<ToastState | null>(null);

  const showToast = useCallback((t: Omit<ToastState, "id">) => {
    setToast({ ...t, id: Date.now() });
  }, []);

  useEffect(() => {
    async function load() {
      try {
        const [s, el] = await Promise.all([getSettings(), getEnvLocked()]);
        setSettings(s);
        setEnvLocked(el.env_locked);
        setUnreachable(false);
      } catch {
        setUnreachable(true);
      }
    }
    void load();
  }, []);

  function getStr(key: string, fallback = ""): string {
    const v = settings?.[key];
    if (typeof v === "string") return v;
    if (typeof v === "number") return String(v);
    return fallback;
  }

  function getIsSet(key: string): boolean {
    const v = settings?.[key];
    if (v && typeof v === "object" && "is_set" in v) {
      return !!(v as { is_set: boolean }).is_set;
    }
    return false;
  }

  function isLocked(key: string): boolean {
    return envLocked.includes(key);
  }

  // Section field states — one hook each to track dirty state per section
  const [llmFields, setLlmFields] = useState({
    llm_base_url: "",
    llm_model: "",
    llm_api_key: "",
  });
  const [llmDirty, setLlmDirty] = useState(false);
  const [llmSaving, setLlmSaving] = useState(false);
  const [llmRestart, setLlmRestart] = useState(false);

  const [sonarrFields, setSonarrFields] = useState({
    sonarr_host: "",
    sonarr_port: "",
    sonarr_api_key: "",
  });
  const [sonarrDirty, setSonarrDirty] = useState(false);
  const [sonarrSaving, setSonarrSaving] = useState(false);
  const [sonarrRestart, setSonarrRestart] = useState(false);

  const [radarrFields, setRadarrFields] = useState({
    radarr_host: "",
    radarr_port: "",
    radarr_api_key: "",
  });
  const [radarrDirty, setRadarrDirty] = useState(false);
  const [radarrSaving, setRadarrSaving] = useState(false);
  const [radarrRestart, setRadarrRestart] = useState(false);

  const [bazarrFields, setBazarrFields] = useState({
    bazarr_host: "",
    bazarr_port: "",
    bazarr_api_key: "",
  });
  const [bazarrDirty, setBazarrDirty] = useState(false);
  const [bazarrSaving, setBazarrSaving] = useState(false);
  const [bazarrRestart, setBazarrRestart] = useState(false);

  const [svcFields, setSvcFields] = useState({
    poll_interval_seconds: "",
    worker_max_concurrent_series: "",
  });
  const [svcDirty, setSvcDirty] = useState(false);
  const [svcSaving, setSvcSaving] = useState(false);
  const [svcRestart, setSvcRestart] = useState(false);

  const [autoTranslate, setAutoTranslate] = useState(false);
  const [autoTranslateDirty, setAutoTranslateDirty] = useState(false);
  const [autoTranslateSaving, setAutoTranslateSaving] = useState(false);

  // Populate from loaded settings
  useEffect(() => {
    if (!settings) return;
    setLlmFields({
      llm_base_url: getStr("llm_base_url"),
      llm_model: getStr("llm_model"),
      llm_api_key: "",
    });
    setSonarrFields({
      sonarr_host: getStr("sonarr_host"),
      sonarr_port: getStr("sonarr_port"),
      sonarr_api_key: "",
    });
    setRadarrFields({
      radarr_host: getStr("radarr_host"),
      radarr_port: getStr("radarr_port"),
      radarr_api_key: "",
    });
    setBazarrFields({
      bazarr_host: getStr("bazarr_host"),
      bazarr_port: getStr("bazarr_port"),
      bazarr_api_key: "",
    });
    setSvcFields({
      poll_interval_seconds: getStr("poll_interval_seconds"),
      worker_max_concurrent_series: getStr("worker_max_concurrent_series"),
    });
    const atVal = settings?.["auto_translate_enabled"];
    setAutoTranslate(typeof atVal === "boolean" ? atVal : false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settings]);

  async function saveSection(
    patch: Record<string, string>,
    setSaving: (v: boolean) => void,
    setDirty: (v: boolean) => void,
    setRestart: (v: boolean) => void,
  ) {
    setSaving(true);
    try {
      // Only send non-empty values (empty secret = user didn't type a new one)
      const filtered = Object.fromEntries(
        Object.entries(patch).filter(([, v]) => v !== ""),
      );
      const result = await putSettings(filtered);
      setDirty(false);
      setRestart(result.restart_required.length > 0);
      showToast({ message: "Settings saved.", variant: "success" });
    } catch {
      showToast({
        message: "Failed to save settings. Check the server logs.",
        variant: "error",
      });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="max-w-3xl">
      <h1 className="text-lg font-semibold text-[#e2e6f0] mb-6">Settings</h1>

      {unreachable && <UnreachableBanner />}

      <div className="flex flex-col gap-6">
        {/* Section 1: LLM Endpoint */}
        <SectionCard>
          <SectionHeading>LLM Endpoint</SectionHeading>
          <FieldGrid>
            <TextField
              id="llm_base_url"
              label="Base URL"
              value={llmFields.llm_base_url}
              onChange={(v) => {
                setLlmFields((f) => ({ ...f, llm_base_url: v }));
                setLlmDirty(true);
              }}
            />
            <TextField
              id="llm_model"
              label="Model"
              value={llmFields.llm_model}
              onChange={(v) => {
                setLlmFields((f) => ({ ...f, llm_model: v }));
                setLlmDirty(true);
              }}
            />
            <MaskedSecretInput
              id="llm_api_key"
              label="API Key"
              isSet={getIsSet("llm_api_key")}
              envLocked={isLocked("llm_api_key")}
              value={llmFields.llm_api_key}
              onChange={(v) => {
                setLlmFields((f) => ({ ...f, llm_api_key: v }));
                setLlmDirty(true);
              }}
            />
          </FieldGrid>
          <div className="flex items-center gap-4">
            <ConnectionTestButton svc="llm" params={llmFields} />
          </div>
          {llmRestart && <RestartBanner />}
          <button
            type="button"
            disabled={!llmDirty || llmSaving}
            onClick={() =>
              saveSection(
                llmFields as Record<string, string>,
                setLlmSaving,
                setLlmDirty,
                setLlmRestart,
              )
            }
            className="h-9 w-full bg-accent text-white text-sm rounded disabled:opacity-50 hover:bg-[#2563eb] focus:outline-[#3b82f6] focus:outline-2 focus:outline-offset-2 transition-colors duration-150"
          >
            {llmSaving ? "Saving…" : "Save Settings"}
          </button>
        </SectionCard>

        {/* Section 2: Sonarr */}
        <SectionCard>
          <SectionHeading>Sonarr</SectionHeading>
          <FieldGrid>
            <TextField
              id="sonarr_host"
              label="Host"
              value={sonarrFields.sonarr_host}
              onChange={(v) => {
                setSonarrFields((f) => ({ ...f, sonarr_host: v }));
                setSonarrDirty(true);
              }}
            />
            <TextField
              id="sonarr_port"
              label="Port"
              value={sonarrFields.sonarr_port}
              type="number"
              onChange={(v) => {
                setSonarrFields((f) => ({ ...f, sonarr_port: v }));
                setSonarrDirty(true);
              }}
            />
            <MaskedSecretInput
              id="sonarr_api_key"
              label="API Key"
              isSet={getIsSet("sonarr_api_key")}
              envLocked={isLocked("sonarr_api_key")}
              value={sonarrFields.sonarr_api_key}
              onChange={(v) => {
                setSonarrFields((f) => ({ ...f, sonarr_api_key: v }));
                setSonarrDirty(true);
              }}
            />
          </FieldGrid>
          <ConnectionTestButton svc="sonarr" params={sonarrFields} />
          {sonarrRestart && <RestartBanner />}
          <button
            type="button"
            disabled={!sonarrDirty || sonarrSaving}
            onClick={() =>
              saveSection(
                sonarrFields as Record<string, string>,
                setSonarrSaving,
                setSonarrDirty,
                setSonarrRestart,
              )
            }
            className="h-9 w-full bg-accent text-white text-sm rounded disabled:opacity-50 hover:bg-[#2563eb] focus:outline-[#3b82f6] focus:outline-2 focus:outline-offset-2 transition-colors duration-150"
          >
            {sonarrSaving ? "Saving…" : "Save Settings"}
          </button>
        </SectionCard>

        {/* Section 3: Radarr */}
        <SectionCard>
          <SectionHeading>Radarr</SectionHeading>
          <FieldGrid>
            <TextField
              id="radarr_host"
              label="Host"
              value={radarrFields.radarr_host}
              onChange={(v) => {
                setRadarrFields((f) => ({ ...f, radarr_host: v }));
                setRadarrDirty(true);
              }}
            />
            <TextField
              id="radarr_port"
              label="Port"
              value={radarrFields.radarr_port}
              type="number"
              onChange={(v) => {
                setRadarrFields((f) => ({ ...f, radarr_port: v }));
                setRadarrDirty(true);
              }}
            />
            <MaskedSecretInput
              id="radarr_api_key"
              label="API Key"
              isSet={getIsSet("radarr_api_key")}
              envLocked={isLocked("radarr_api_key")}
              value={radarrFields.radarr_api_key}
              onChange={(v) => {
                setRadarrFields((f) => ({ ...f, radarr_api_key: v }));
                setRadarrDirty(true);
              }}
            />
          </FieldGrid>
          <ConnectionTestButton svc="radarr" params={radarrFields} />
          {radarrRestart && <RestartBanner />}
          <button
            type="button"
            disabled={!radarrDirty || radarrSaving}
            onClick={() =>
              saveSection(
                radarrFields as Record<string, string>,
                setRadarrSaving,
                setRadarrDirty,
                setRadarrRestart,
              )
            }
            className="h-9 w-full bg-accent text-white text-sm rounded disabled:opacity-50 hover:bg-[#2563eb] focus:outline-[#3b82f6] focus:outline-2 focus:outline-offset-2 transition-colors duration-150"
          >
            {radarrSaving ? "Saving…" : "Save Settings"}
          </button>
        </SectionCard>

        {/* Section 4: Bazarr */}
        <SectionCard>
          <SectionHeading>Bazarr</SectionHeading>
          <FieldGrid>
            <TextField
              id="bazarr_host"
              label="Host"
              value={bazarrFields.bazarr_host}
              onChange={(v) => {
                setBazarrFields((f) => ({ ...f, bazarr_host: v }));
                setBazarrDirty(true);
              }}
            />
            <TextField
              id="bazarr_port"
              label="Port"
              value={bazarrFields.bazarr_port}
              type="number"
              onChange={(v) => {
                setBazarrFields((f) => ({ ...f, bazarr_port: v }));
                setBazarrDirty(true);
              }}
            />
            <MaskedSecretInput
              id="bazarr_api_key"
              label="API Key"
              isSet={getIsSet("bazarr_api_key")}
              envLocked={isLocked("bazarr_api_key")}
              value={bazarrFields.bazarr_api_key}
              onChange={(v) => {
                setBazarrFields((f) => ({ ...f, bazarr_api_key: v }));
                setBazarrDirty(true);
              }}
            />
          </FieldGrid>
          <ConnectionTestButton svc="bazarr" params={bazarrFields} />
          {bazarrRestart && <RestartBanner />}
          <button
            type="button"
            disabled={!bazarrDirty || bazarrSaving}
            onClick={() =>
              saveSection(
                bazarrFields as Record<string, string>,
                setBazarrSaving,
                setBazarrDirty,
                setBazarrRestart,
              )
            }
            className="h-9 w-full bg-accent text-white text-sm rounded disabled:opacity-50 hover:bg-[#2563eb] focus:outline-[#3b82f6] focus:outline-2 focus:outline-offset-2 transition-colors duration-150"
          >
            {bazarrSaving ? "Saving…" : "Save Settings"}
          </button>
        </SectionCard>

        {/* Section 5: Path Mappings */}
        <SectionCard>
          <SectionHeading>Path Mappings</SectionHeading>
          <p className="text-xs text-[#6b7280]">
            Map host paths to container paths so Trezarr can resolve subtitle
            file paths from the Sonarr/Radarr API.
          </p>
          <p className="text-xs text-[#6b7280]">
            Path mapping configuration is available via the config file{" "}
            <code className="font-mono">/config/config.yaml</code>.
          </p>
        </SectionCard>

        {/* Section 6: Service Settings */}
        <SectionCard>
          <SectionHeading>Service Settings</SectionHeading>
          <FieldGrid>
            <TextField
              id="poll_interval_seconds"
              label="Poll Interval (seconds)"
              value={svcFields.poll_interval_seconds}
              type="number"
              onChange={(v) => {
                setSvcFields((f) => ({ ...f, poll_interval_seconds: v }));
                setSvcDirty(true);
              }}
            />
            <TextField
              id="worker_max_concurrent_series"
              label="Max Concurrent Series"
              value={svcFields.worker_max_concurrent_series}
              type="number"
              onChange={(v) => {
                setSvcFields((f) => ({
                  ...f,
                  worker_max_concurrent_series: v,
                }));
                setSvcDirty(true);
              }}
            />
          </FieldGrid>
          {svcRestart && <RestartBanner />}
          <button
            type="button"
            disabled={!svcDirty || svcSaving}
            onClick={() =>
              saveSection(
                svcFields as Record<string, string>,
                setSvcSaving,
                setSvcDirty,
                setSvcRestart,
              )
            }
            className="h-9 w-full bg-accent text-white text-sm rounded disabled:opacity-50 hover:bg-[#2563eb] focus:outline-[#3b82f6] focus:outline-2 focus:outline-offset-2 transition-colors duration-150"
          >
            {svcSaving ? "Saving…" : "Save Settings"}
          </button>
        </SectionCard>

        {/* Section 7: Auto-translate safety gate */}
        <SectionCard>
          <SectionHeading>Auto-translate</SectionHeading>
          <div className="flex flex-col gap-1">
            <label className="flex items-center gap-3 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={autoTranslate}
                onChange={(e) => {
                  setAutoTranslate(e.target.checked);
                  setAutoTranslateDirty(true);
                }}
                className="w-4 h-4 rounded border-[#2d3148] accent-[#3b82f6]"
              />
              <span className="text-sm text-[#e2e6f0]">
                Auto-translate eligible library on a schedule
              </span>
            </label>
            <p className="text-xs text-[#6b7280] ml-7">
              When OFF, the daemon discovers items but never translates automatically.
              Manual translate via Library is always available.
            </p>
          </div>
          <button
            type="button"
            disabled={!autoTranslateDirty || autoTranslateSaving}
            onClick={async () => {
              setAutoTranslateSaving(true);
              try {
                await putSettings({ auto_translate_enabled: autoTranslate });
                setAutoTranslateDirty(false);
                showToast({ message: "Settings saved.", variant: "success" });
              } catch {
                showToast({
                  message: "Failed to save settings. Check the server logs.",
                  variant: "error",
                });
              } finally {
                setAutoTranslateSaving(false);
              }
            }}
            className="h-9 w-full bg-accent text-white text-sm rounded disabled:opacity-50 hover:bg-[#2563eb] focus:outline-[#3b82f6] focus:outline-2 focus:outline-offset-2 transition-colors duration-150"
          >
            {autoTranslateSaving ? "Saving…" : "Save Settings"}
          </button>
        </SectionCard>
      </div>

      <Toast toast={toast} onDismiss={() => setToast(null)} />
    </div>
  );
}
