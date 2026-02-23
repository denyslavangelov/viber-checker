"use client";

import { useState, useRef, useEffect } from "react";
import UserIcon from "@/components/icons/user-icon";
import PhoneIcon from "@/components/icons/phone-icon";
import type { AnimatedIconHandle } from "@/components/icons/types";

interface ApiResponse {
  number: string;
  error?: string;
  panel_base64?: string;
  contact_name?: string;
  panel_text?: string;
}

export default function Home() {
  const [agentUrl, setAgentUrl] = useState(() => {
    if (typeof window === "undefined") return "";
    const pub = process.env.NEXT_PUBLIC_AGENT_URL?.trim();
    if (pub) return pub;
    return window.location.origin + "/api/agent";
  });

  useEffect(() => {
    if (process.env.NEXT_PUBLIC_AGENT_URL?.trim()) return;
    setAgentUrl(window.location.origin + "/api/agent");
  }, []);

  const [mode, setMode] = useState<"lookup" | "send">("lookup");
  const [number, setNumber] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [panelImage, setPanelImage] = useState<string | null>(null);
  const [contactName, setContactName] = useState<string | null>(null);
  const [lookedUpNumber, setLookedUpNumber] = useState<string | null>(null);
  const [sendSuccess, setSendSuccess] = useState(false);
  const userIconRef = useRef<AnimatedIconHandle>(null);
  const phoneIconRef = useRef<AnimatedIconHandle>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const hasResult = !!(panelImage || contactName || lookedUpNumber);
  const showSendForm = mode === "send" && !hasResult && !sendSuccess;
  const showSendSuccess = mode === "send" && sendSuccess;

  function handleCheckAnother() {
    setPanelImage(null);
    setContactName(null);
    setLookedUpNumber(null);
    setNumber("");
    setError(null);
    inputRef.current?.focus();
  }

  function handleSendAnother() {
    setSendSuccess(false);
    setMessage("");
    setError(null);
  }

  async function handleSendMessage(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSendSuccess(false);

    const base = agentUrl.trim().replace(/\/$/, "");
    if (!base || !number.trim()) {
      setError("Въведете телефонен номер");
      return;
    }
    if (!message.trim()) {
      setError("Въведете съобщение");
      return;
    }

    setLoading(true);
    try {
      const res = await fetch(`${base}/send-message`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          number: number.trim(),
          message: message.trim(),
        }),
      });

      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        setError((data as { error?: string }).error || "Заявката не успя");
        return;
      }
      setSendSuccess(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Заявката не успя");
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setPanelImage(null);
    setContactName(null);
    setLookedUpNumber(null);

    const base = agentUrl.trim().replace(/\/$/, "");
    if (!base || !number.trim()) {
      setError("Въведете телефонен номер");
      return;
    }

    setLoading(true);
    try {
      const res = await fetch(`${base}/check-number-base64`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          number: number.trim(),
          only_panel: true,
        }),
      });

      const data: ApiResponse = await res.json();

      if (!res.ok) {
        setError(data.error || "Заявката не успя");
        return;
      }

      const name = (data.contact_name ?? "").trim();
      if (!name) {
        setError("Контактът не беше намерен.");
        return;
      }

      if (data.panel_base64) setPanelImage(data.panel_base64);
      setContactName(name);
      setLookedUpNumber((data.number || number).trim());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Заявката не успя");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen flex flex-col items-center justify-center p-4 sm:p-6 bg-[#0a0a0c] pt-[env(safe-area-inset-top)]">
      <div className="w-full max-w-[32rem] min-w-0">
        <div
          className={`rounded-2xl sm:rounded-3xl border border-white/[0.1] bg-white/[0.06] shadow-xl shadow-black/30 backdrop-blur-sm overflow-hidden transition-all duration-300 ${
            hasResult ? "animate-card-glow card-motion" : ""
          }`}
        >
          <form
            onSubmit={mode === "send" ? handleSendMessage : handleSubmit}
            className="flex flex-col"
          >
            {/* Mode toggle */}
            {!hasResult && !showSendSuccess && (
              <div className="flex rounded-xl bg-white/[0.06] p-1 mx-4 sm:mx-6 md:mx-9 mt-4 sm:mt-6">
                <button
                  type="button"
                  onClick={() => { setMode("lookup"); setError(null); }}
                  className={`flex-1 rounded-lg py-2.5 text-sm font-medium transition-all ${
                    mode === "lookup"
                      ? "bg-white text-black"
                      : "text-white/70 hover:text-white"
                  }`}
                >
                  Търси
                </button>
                <button
                  type="button"
                  onClick={() => { setMode("send"); setError(null); setSendSuccess(false); }}
                  className={`flex-1 rounded-lg py-2.5 text-sm font-medium transition-all ${
                    mode === "send"
                      ? "bg-white text-black"
                      : "text-white/70 hover:text-white"
                  }`}
                >
                  Изпрати съобщение
                </button>
              </div>
            )}

            {!hasResult && !showSendForm && !showSendSuccess && (
              <div className="px-4 sm:px-6 md:px-9 pt-4 sm:pt-6 pb-4 sm:pb-5 space-y-4">
                <input
                  ref={inputRef}
                  type="tel"
                  inputMode="numeric"
                  autoComplete="tel"
                  value={number}
                  onChange={(e) => setNumber(e.target.value)}
                  placeholder="+359 89 428 8133"
                  className="w-full rounded-xl border border-white/[0.08] bg-white/[0.04] px-4 py-3.5 sm:py-3 text-white placeholder-white/30 focus:border-white/20 focus:outline-none focus:ring-2 focus:ring-white/10 text-center text-base sm:text-[1.05rem] tracking-tight transition-all duration-200 min-h-[48px]"
                />
              </div>
            )}

            {showSendForm && (
              <div className="px-4 sm:px-6 md:px-9 pt-4 sm:pt-6 pb-4 sm:pb-5 space-y-4">
                <input
                  type="tel"
                  inputMode="numeric"
                  autoComplete="tel"
                  value={number}
                  onChange={(e) => setNumber(e.target.value)}
                  placeholder="+359 89 428 8133"
                  className="w-full rounded-xl border border-white/[0.08] bg-white/[0.04] px-4 py-3.5 sm:py-3 text-white placeholder-white/30 focus:border-white/20 focus:outline-none focus:ring-2 focus:ring-white/10 text-center text-base sm:text-[1.05rem] tracking-tight transition-all duration-200 min-h-[48px]"
                />
                <textarea
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  placeholder="Текст на съобщението..."
                  rows={3}
                  className="w-full rounded-xl border border-white/[0.08] bg-white/[0.04] px-4 py-3 text-white placeholder-white/30 focus:border-white/20 focus:outline-none focus:ring-2 focus:ring-white/10 resize-none text-base min-h-[80px]"
                />
              </div>
            )}

            {error && (
              <p className="px-4 sm:px-6 md:px-9 pb-2 text-center text-sm text-red-400/90 animate-fade-slide-in">
                {error}
              </p>
            )}

            {loading && (
              <div
                className="flex items-center justify-center gap-3 sm:gap-4 px-4 sm:px-6 md:px-9 py-6 sm:py-8 border-t border-white/[0.08] animate-fade-slide-in min-h-[140px] sm:min-h-[174px]"
                aria-live="polite"
                aria-busy="true"
              >
                <div
                  className="flex-shrink-0 w-10 h-10 rounded-full border-2 border-white/20 border-t-white/80 animate-spin-slow"
                  aria-hidden
                />
                <div className="flex flex-col items-start gap-1">
                  <p className="text-lg font-medium text-white/90">
                    {mode === "send" ? "Изпращам…" : "Търся…"}
                  </p>
                </div>
              </div>
            )}

            {showSendSuccess && (
              <div className="px-4 sm:px-6 md:px-9 py-6 sm:py-8 border-t border-white/[0.08] animate-fade-slide-in text-center">
                <p className="text-lg font-medium text-white/90">Съобщението беше изпратено.</p>
                <p className="text-sm text-white/50 mt-1">Viber беше затворен.</p>
              </div>
            )}

            {hasResult && (
              <div className="flex flex-col sm:flex-row items-center sm:items-stretch gap-4 sm:gap-6 md:gap-9 px-4 sm:px-6 md:px-9 py-5 border-t border-white/[0.08] animate-fade-slide-in min-h-[140px] sm:min-h-[174px]">
                {panelImage && (
                  <div
                    className="flex-shrink-0 rounded-full overflow-hidden ring-2 ring-white/10 bg-white/5 animate-scale-in w-24 h-24 sm:w-28 sm:h-28 md:w-[132px] md:h-[132px]"
                    style={{ animationDelay: "0.05s", animationFillMode: "both" }}
                  >
                    <img
                      src={`data:image/png;base64,${panelImage}`}
                      alt=""
                      className="w-full h-full object-cover"
                    />
                  </div>
                )}
                <div className="flex flex-col min-w-0 flex-1 justify-center py-1 overflow-hidden w-full text-center sm:text-left">
                  {contactName && (
                    <div
                      className="flex items-center justify-center sm:justify-start gap-3 sm:gap-4 min-h-[2.5rem] sm:min-h-[3.375rem] animate-slide-in-right opacity-0"
                      style={{ animationDelay: "0.15s", animationFillMode: "both" }}
                    >
                      <span
                        className="flex-shrink-0 flex items-center justify-center rounded-xl bg-white/[0.08] text-white/70 w-10 h-10 sm:w-[42px] sm:h-[42px]"
                        aria-hidden
                        onMouseEnter={() => userIconRef.current?.startAnimation()}
                        onMouseLeave={() => userIconRef.current?.stopAnimation()}
                        onTouchStart={() => userIconRef.current?.startAnimation()}
                        onTouchEnd={() => userIconRef.current?.stopAnimation()}
                      >
                        <UserIcon ref={userIconRef} size={24} strokeWidth={2} />
                      </span>
                      <p className="text-xl sm:text-2xl md:text-3xl font-semibold text-white tracking-tight truncate leading-tight">
                        {contactName}
                      </p>
                    </div>
                  )}
                  {contactName && lookedUpNumber && (
                    <div
                      className="my-2 sm:my-2.5 h-px bg-white/[0.08] animate-line-expand opacity-0"
                      style={{ animationDelay: "0.3s", animationFillMode: "both" }}
                      role="presentation"
                    />
                  )}
                  {lookedUpNumber && (
                    <div
                      className="flex items-center justify-center sm:justify-start gap-3 sm:gap-4 min-h-[2.5rem] sm:min-h-[3rem] animate-slide-in-right opacity-0"
                      style={{ animationDelay: "0.4s", animationFillMode: "both" }}
                    >
                      <span
                        className="flex-shrink-0 flex items-center justify-center rounded-xl bg-white/[0.08] text-white/70 w-10 h-10 sm:w-[42px] sm:h-[42px]"
                        aria-hidden
                        onMouseEnter={() => phoneIconRef.current?.startAnimation()}
                        onMouseLeave={() => phoneIconRef.current?.stopAnimation()}
                        onTouchStart={() => phoneIconRef.current?.startAnimation()}
                        onTouchEnd={() => phoneIconRef.current?.stopAnimation()}
                      >
                        <PhoneIcon ref={phoneIconRef} size={24} strokeWidth={2} />
                      </span>
                      <p className="text-lg sm:text-xl text-white/80 tracking-tight truncate tabular-nums">
                        {lookedUpNumber}
                      </p>
                    </div>
                  )}
                </div>
              </div>
            )}

            <div className="px-4 sm:px-6 md:px-9 pt-4 pb-[max(1.5rem,env(safe-area-inset-bottom))]">
              {hasResult ? (
                <button
                  type="button"
                  onClick={handleCheckAnother}
                  className="w-full rounded-xl border border-white/20 bg-white/5 py-3.5 sm:py-3 font-semibold text-white hover:bg-white/10 active:scale-[0.99] transition-all duration-200 min-h-[48px] touch-manipulation"
                >
                  Провери друг номер
                </button>
              ) : showSendSuccess ? (
                <button
                  type="button"
                  onClick={handleSendAnother}
                  className="w-full rounded-xl border border-white/20 bg-white/5 py-3.5 sm:py-3 font-semibold text-white hover:bg-white/10 active:scale-[0.99] transition-all duration-200 min-h-[48px] touch-manipulation"
                >
                  Изпрати друго
                </button>
              ) : (
                <button
                  type="submit"
                  disabled={loading}
                  className="w-full rounded-xl bg-white py-3.5 sm:py-3 font-semibold text-black hover:bg-white/95 active:scale-[0.99] disabled:opacity-50 disabled:cursor-not-allowed disabled:active:scale-100 transition-all duration-200 min-h-[48px] touch-manipulation"
                >
                  {loading ? "…" : mode === "send" ? "Изпрати" : "Търси"}
                </button>
              )}
            </div>
          </form>
        </div>
      </div>
    </main>
  );
}
