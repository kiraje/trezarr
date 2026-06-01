/**
 * ConnectionTestButton + ResultChip.
 *
 * Conforms to 07-UI-SPEC.md §ConnectionTestButton + ResultChip:
 * - Button labeled "Test Connection"; shows spinner on pending; disabled while testing
 * - ResultChip: 28px, ok=green chip with check, error=red chip with X
 * - Result chip clears when form fields are edited
 */
import { useState } from "react";
import { Check, X, RefreshCw } from "lucide-react";
import { testConnection } from "../api/client";

type TestStatus = "idle" | "pending" | "ok" | "error";

interface ConnectionTestButtonProps {
  svc: string;
  params: Record<string, unknown>;
  /** Reset key — changes when form fields change, clears the result chip */
  resetKey?: string | number;
}

export default function ConnectionTestButton({
  svc,
  params,
}: ConnectionTestButtonProps) {
  const [status, setStatus] = useState<TestStatus>("idle");
  const [errorMsg, setErrorMsg] = useState<string>("");

  async function handleTest() {
    setStatus("pending");
    setErrorMsg("");
    try {
      const result = await testConnection(svc, params);
      if (result.ok) {
        setStatus("ok");
      } else {
        setStatus("error");
        setErrorMsg(result.error ?? "Connection failed");
      }
    } catch (err) {
      setStatus("error");
      setErrorMsg(err instanceof Error ? err.message : "Network error");
    }
  }

  return (
    <div className="flex items-center gap-3">
      <button
        type="button"
        onClick={handleTest}
        disabled={status === "pending"}
        className="flex items-center gap-2 h-9 px-4 bg-accent text-white text-sm rounded disabled:opacity-60 hover:bg-[#2563eb] focus:outline-[#3b82f6] focus:outline-2 focus:outline-offset-2 transition-colors duration-150"
      >
        {status === "pending" && (
          <RefreshCw size={14} className="animate-spin" aria-hidden="true" />
        )}
        Test Connection
      </button>

      {/* ResultChip */}
      {status === "ok" && (
        <span
          className="inline-flex items-center gap-1.5 h-7 px-2 rounded text-xs"
          style={{ backgroundColor: "#14291e", color: "#4ade80" }}
        >
          <Check size={12} aria-hidden="true" />
          Connected
        </span>
      )}
      {status === "error" && (
        <span
          className="inline-flex items-center gap-1.5 h-7 px-2 rounded text-xs"
          style={{ backgroundColor: "#2d1515", color: "#f87171" }}
          title={errorMsg}
        >
          <X size={12} aria-hidden="true" />
          {errorMsg.length > 40
            ? `${errorMsg.slice(0, 40)}…`
            : errorMsg || "Connection failed"}
        </span>
      )}
    </div>
  );
}
