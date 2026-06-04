/**
 * ConnectionTestButton + ResultChip.
 *
 * Conforms to 07-UI-SPEC.md §ConnectionTestButton + ResultChip:
 * - Button labeled "Test Connection"; shows spinner on pending; disabled while testing
 * - ResultChip: 28px, ok=green chip with check, error=red chip with X
 * - Result chip clears when form fields are edited
 */
import { useState, useEffect } from "react";
import { Check, X, RefreshCw } from "lucide-react";
import { testConnection } from "../api/client";
import { Button } from "./ui/button";

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
  resetKey,
}: ConnectionTestButtonProps) {
  const [status, setStatus] = useState<TestStatus>("idle");
  const [errorMsg, setErrorMsg] = useState<string>("");

  // Clear the result chip whenever resetKey changes (i.e., form fields changed)
  useEffect(() => {
    setStatus("idle");
    setErrorMsg("");
  }, [resetKey]);

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
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={handleTest}
        disabled={status === "pending"}
      >
        {status === "pending" && (
          <RefreshCw size={14} className="animate-spin" aria-hidden="true" />
        )}
        Test Connection
      </Button>

      {/* ResultChip */}
      {status === "ok" && (
        <span
          className="inline-flex items-center gap-1.5 h-7 px-2 rounded text-xs bg-emerald-900/50 text-emerald-400"
        >
          <Check size={12} aria-hidden="true" />
          Connected
        </span>
      )}
      {status === "error" && (
        <span
          className="inline-flex items-center gap-1.5 h-7 px-2 rounded text-xs bg-destructive/10 text-destructive"
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
