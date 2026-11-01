"use client";
// The support portal: identity rail, the conversation, and the trust panels (citations, why, trace).
// Token and conversation live in sessionStorage: the server binds a conversation to the sign-in session.
import { useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import { ChatClient, HttpError, readClaims, type Claims } from "@/lib/chat-client.ts";
import { addUserMessage, initialState, reduce, type ChatState, type Citation, type Message } from "@/lib/reduce.ts";
import type { Trace, Why } from "@/lib/trace.ts";
import { Icon, Logo, type IconName } from "./icons.tsx";
import { CitationView, Drawer, TraceView, WhyPanel, type Loadable } from "./panels.tsx";

const LIMIT = 16384; // channels.api.envelope.TurnRequest
const DISCLOSURE = "You are chatting with an AI assistant."; // safety/governance/disclosure.py
const HELP_URL = process.env.NEXT_PUBLIC_HELP_CENTER_URL;
const SUGGESTIONS = ["How do I reset my password?", "How do refunds work?", "Where can I find my invoices?"];
const TIERS: Record<string, { short: string; label: string }> = {
  T0_ANON: { short: "T0", label: "Guest" },
  T1_VERIFIED: { short: "T1", label: "Signed in" },
  T2_SSO: { short: "T2", label: "Signed in" },
};

type Panel = { kind: "trace"; turnId: string } | { kind: "citation"; citation: Citation } | null;
type Otp = { stage: "email" | "code"; email: string; code: string; challengeId?: string; busy?: boolean; error?: string };

const store = {
  read(key: string) {
    try { return JSON.parse(sessionStorage.getItem(key) ?? "null"); } catch { return null; }
  },
  write(key: string, value: unknown) {
    try { sessionStorage.setItem(key, JSON.stringify(value)); } catch { /* private mode: not kept */ }
  },
};

const clock = (at?: number) => at ? new Date(at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) : "";

export default function Portal({ tenantId }: { tenantId: string }) {
  const client = useRef<ChatClient | null>(null);
  const stream = useRef<AbortController | null>(null);
  const storageKey = `support-agent:${tenantId}:session`;
  const [claims, setClaims] = useState<Claims | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [chat, setChat] = useState<ChatState>(initialState);
  const [lost, setLost] = useState(false);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [panel, setPanel] = useState<Panel>(null);
  const [traces, setTraces] = useState<Record<string, Loadable<Trace>>>({});
  const [whys, setWhys] = useState<Record<string, Loadable<Why[]> | undefined>>({});
  const [otp, setOtp] = useState<Otp>({ stage: "email", email: "", code: "" });
  const [railOpen, setRailOpen] = useState(false);
  const thread = useRef<HTMLDivElement>(null);

  const remember = useCallback((conversation: string) => {
    store.write(storageKey, { token: client.current!.token, conversationId: conversation });
  }, [storageKey]);

  const open = useCallback((conversation: string) => {
    stream.current?.abort();
    const controller = new AbortController();
    stream.current = controller;
    const api = client.current!;
    api.lastEventId = null;
    setConversationId(conversation);
    setChat(initialState());
    setTraces({});
    setWhys({});
    setPanel(null);
    setLost(false);
    remember(conversation);
    api.listen(conversation, (event) => setChat((state) => reduce(state, { ...event, at: Date.now() })),
      { signal: controller.signal }).catch(() => {
      if (!controller.signal.aborted) setLost(true);
    });
  }, [remember]);

  const fresh = useCallback(async () => {
    const api = client.current!;
    await api.signInAnonymous(tenantId);
    setClaims(readClaims(api.token));
    setOtp({ stage: "email", email: "", code: "" });
    open(api.uuid());
  }, [open, tenantId]);

  useEffect(() => {
    client.current = new ChatClient();
    const saved = store.read(storageKey);
    const savedClaims = readClaims(saved?.token ?? null);
    if (savedClaims && savedClaims.tid === tenantId && savedClaims.exp * 1000 > Date.now() + 60_000) {
      client.current.token = saved.token;
      setClaims(savedClaims);
      open(saved.conversationId);
    } else {
      fresh().catch(() => setLost(true));
    }
    return () => stream.current?.abort();
  }, [fresh, open, storageKey, tenantId]);

  useEffect(() => {
    thread.current?.scrollTo({ top: thread.current.scrollHeight, behavior: "smooth" });
  }, [chat]);

  async function send(text: string) {
    const content = text.trim();
    if (!content || sending || !conversationId) return;
    setSending(true);
    setInput("");
    setChat((state) => addUserMessage(state, content, Date.now()));
    try {
      await client.current!.send(conversationId, content);
    } catch (error) {
      setInput(content);
      setChat((state) => ({ ...state, error: `Not sent (${(error as Error).message}). Your text is back in the box.` }));
    } finally {
      setSending(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    send(input);
  }

  function onKey(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      send(input);
    }
  }

  async function loadTrace(turnId: string) {
    setPanel({ kind: "trace", turnId });
    if (traces[turnId]?.state === "ready") return;
    setTraces((all) => ({ ...all, [turnId]: { state: "loading" } }));
    try {
      const value = await client.current!.trace(conversationId!, turnId);
      setTraces((all) => ({ ...all, [turnId]: { state: "ready", value } }));
    } catch (error) {
      const message = error instanceof HttpError && error.status === 404
        ? "The record of this answer is still being written. Try again in a moment."
        : "Could not load how this was answered.";
      setTraces((all) => ({ ...all, [turnId]: { state: "error", message } }));
    }
  }

  async function toggleWhy(turnId: string) {
    if (whys[turnId]) {
      setWhys((all) => ({ ...all, [turnId]: undefined }));
      return;
    }
    setWhys((all) => ({ ...all, [turnId]: { state: "loading" } }));
    try {
      const value = await client.current!.why(conversationId!, turnId);
      setWhys((all) => ({ ...all, [turnId]: { state: "ready", value } }));
    } catch {
      setWhys((all) => ({ ...all, [turnId]: { state: "error", message: "Could not load why this answer was given." } }));
    }
  }

  async function startOtp(event: FormEvent) {
    event.preventDefault();
    setOtp((o) => ({ ...o, busy: true, error: undefined }));
    try {
      const challengeId = await client.current!.startOtp(tenantId, otp.email.trim());
      setOtp((o) => ({ ...o, stage: "code", challengeId, busy: false }));
    } catch {
      setOtp((o) => ({ ...o, busy: false, error: "Could not send a code. Check the address and try again." }));
    }
  }

  async function verifyOtp(event: FormEvent) {
    event.preventDefault();
    setOtp((o) => ({ ...o, busy: true, error: undefined }));
    try {
      await client.current!.verifyOtp(tenantId, otp.challengeId!, otp.code.trim());
      setClaims(readClaims(client.current!.token));
      remember(conversationId!);
      setTraces({}); // the trace shows more once signed in
      setOtp({ stage: "email", email: "", code: "" });
    } catch {
      setOtp((o) => ({ ...o, busy: false, error: "That code did not work. Check it, or send a new one." }));
    }
  }

  async function logout() {
    try { await client.current!.logout(); } catch { /* the session is dropped locally either way */ }
    await fresh().catch(() => setLost(true));
  }

  const tier = TIERS[claims?.tier ?? "T0_ANON"];
  const anonymous = !claims || claims.tier === "T0_ANON";
  const navItem = "flex items-center gap-3 rounded-lg px-3 py-2.5 text-[15px]";

  const rail = (
    <nav aria-label="Portal" className="flex h-full w-[264px] flex-col bg-rail px-4 py-5 text-rail-ink">
      <div className="mb-7 flex items-center gap-3 px-1">
        <Logo className="size-9 text-rail-ink" />
        <div>
          <p className="text-lg font-semibold leading-tight">Support Portal</p>
          <p className="text-xs text-rail-muted">Enterprise Support</p>
        </div>
      </div>
      <p className="mb-2 px-1 text-[11px] font-semibold tracking-wider text-rail-muted">NAVIGATION</p>
      <ul className="space-y-1">
        <li>
          <span aria-current="page" className={`${navItem} border-l-[3px] border-brand bg-brand/20 font-medium`}>
            <Icon name="chat" /> Chat
          </span>
        </li>
        <li>
          <span aria-disabled="true" className={`${navItem} text-rail-muted`}>
            <Icon name="history" /> History
            <span className="ml-auto rounded-md bg-rail-raised px-2 py-0.5 text-[11px]">Disabled</span>
          </span>
        </li>
        {HELP_URL && (
          <li>
            <a href={HELP_URL} target="_blank" rel="noreferrer" className={`${navItem} hover:bg-rail-raised`}>
              <Icon name="help" /> Help center <Icon name="external" className="ml-auto size-4" />
            </a>
          </li>
        )}
      </ul>

      <p className="mb-2 mt-7 px-1 text-[11px] font-semibold tracking-wider text-rail-muted">SIGN IN</p>
      <div className="space-y-2">
        <div className={`flex items-center gap-3 rounded-lg border px-3 py-2.5 ${anonymous
          ? "border-brand/50 bg-rail-raised" : "border-rail-line"}`}>
          <Icon name="user" className="size-5 text-brand-strong" />
          <span className="flex-1">
            <span className="block text-sm font-medium">Anonymous</span>
            <span className="block text-xs text-rail-muted">Continue without signing in</span>
          </span>
          {anonymous && <Icon name="check" className="size-5 text-brand-strong" />}
        </div>

        <div className={`rounded-lg border px-3 py-2.5 ${!anonymous ? "border-brand/50 bg-rail-raised" : "border-rail-line"}`}>
          <div className="flex items-center gap-3">
            <Icon name="mail" className="size-5 text-rail-muted" />
            <span className="flex-1">
              <span className="block text-sm font-medium">Email code (OTP)</span>
              <span className="block truncate text-xs text-rail-muted">
                {anonymous ? "Get a code sent to your email" : `Verified as ${claims?.sub}`}
              </span>
            </span>
            {!anonymous && <Icon name="check" className="size-5 text-brand-strong" />}
          </div>
          {anonymous && (otp.stage === "email" ? (
            <form onSubmit={startOtp} className="mt-3 space-y-2">
              <label htmlFor="otp-email" className="block text-xs text-rail-muted">Work email</label>
              <input id="otp-email" type="email" required autoComplete="email" placeholder="you@company.com"
                value={otp.email} onChange={(e) => setOtp((o) => ({ ...o, email: e.target.value }))}
                className="w-full rounded-md border border-rail-line bg-rail px-3 py-2 text-sm placeholder:text-rail-muted focus:border-brand focus:outline-none" />
              <button disabled={otp.busy} className="flex w-full items-center justify-center gap-2 rounded-md bg-brand py-2 text-sm font-medium text-white hover:bg-brand-strong disabled:opacity-60">
                Send code <Icon name="right" className="size-4" />
              </button>
            </form>
          ) : (
            <form onSubmit={verifyOtp} className="mt-3 space-y-2">
              <label htmlFor="otp-code" className="block text-xs text-rail-muted">Code sent to {otp.email}</label>
              <input id="otp-code" inputMode="numeric" autoComplete="one-time-code" required value={otp.code}
                onChange={(e) => setOtp((o) => ({ ...o, code: e.target.value }))}
                className="w-full rounded-md border border-rail-line bg-rail px-3 py-2 font-mono text-sm tracking-widest focus:border-brand focus:outline-none" />
              <button disabled={otp.busy} className="w-full rounded-md bg-brand py-2 text-sm font-medium text-white hover:bg-brand-strong disabled:opacity-60">
                Verify
              </button>
              <button type="button" onClick={() => setOtp({ stage: "email", email: otp.email, code: "" })}
                className="w-full text-xs text-rail-muted hover:text-rail-ink">Use a different address</button>
              {process.env.NODE_ENV !== "production" && (
                <p className="text-[11px] text-rail-muted">Development: the code is printed in the API log.</p>
              )}
            </form>
          ))}
          {otp.error && <p role="alert" className="mt-2 text-xs text-[#ffb4ab]">{otp.error}</p>}
        </div>

        <div className="rounded-lg border border-rail-line bg-rail-raised/50 px-3 py-2.5 opacity-80">
          <div className="flex items-center gap-3">
            <Icon name="building" className="size-5 text-rail-muted" />
            <span className="flex-1">
              <span className="block text-sm font-medium">Enterprise SSO</span>
              <span className="block text-xs text-rail-muted">Single sign-on</span>
            </span>
          </div>
          <span className="mt-2 inline-block rounded-md bg-rail-line px-2 py-0.5 text-[11px]">Coming soon</span>
        </div>
      </div>

      <button onClick={logout} className={`${navItem} mt-auto border-t border-rail-line pt-4 hover:bg-rail-raised`}>
        <Icon name="logout" /> Log out
      </button>
    </nav>
  );

  return (
    <div className="flex h-dvh overflow-hidden">
      <div className="hidden md:block">{rail}</div>
      {railOpen && (
        <div className="fixed inset-0 z-50 flex md:hidden">
          {rail}
          <button aria-label="Close menu" className="flex-1 bg-black/40" onClick={() => setRailOpen(false)} />
        </div>
      )}

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-3 border-b border-line bg-surface px-4 py-3 sm:px-6">
          <button aria-label="Open menu" onClick={() => setRailOpen(true)} className="rounded-md p-1.5 text-muted md:hidden">
            <Icon name="menu" />
          </button>
          <div className="min-w-0 flex-1">
            <h1 className="text-xl font-semibold">Chat</h1>
            <p className="hidden truncate text-sm text-muted sm:block">Get answers from our documentation and knowledge base.</p>
          </div>
          <span className="hidden items-center gap-1.5 text-sm text-muted 2xl:flex">
            <Icon name="shield" className="size-4" /> Enterprise Secure · Trusted Content
          </span>
          <span className="flex items-center gap-2 text-sm font-medium" aria-label={`${tier.label}, tier ${tier.short}`}>
            <span className="hidden sm:inline">{tier.label}</span>
            <span className="rounded-md border border-[#e0a458] bg-[#fff6ea] px-1.5 py-0.5 font-mono text-xs text-[#a35a00] dark:bg-transparent">
              {tier.short}
            </span>
          </span>
          <button onClick={() => open(client.current!.uuid())} title="New conversation"
            className="flex items-center gap-1.5 rounded-full bg-brand px-3 py-2 text-sm font-medium text-white hover:bg-brand-strong">
            <Icon name="plus" className="size-4" /><span className="hidden sm:inline">New conversation</span>
          </button>
        </header>

        <div className="mx-4 mt-4 flex items-start gap-3 rounded-xl border border-warn-line bg-warn-bg px-4 py-3 text-warn-ink sm:mx-6">
          <Icon name="warn" className="mt-0.5 size-5 shrink-0" />
          <p className="text-sm">
            <strong className="font-semibold">{DISCLOSURE}</strong> A person can take over at any time. Every answer
            shows its sources, why it was given and how it was answered.
          </p>
        </div>

        <div ref={thread} className="flex-1 overflow-y-auto px-4 py-5 sm:px-6">
          <div className="mx-auto flex max-w-3xl flex-col gap-5">
            {chat.messages.length === 0 && !chat.status && (
              <div className="py-10 text-center">
                <Icon name="spark" className="mx-auto mb-3 size-8 text-brand" />
                <p className="font-medium">How can we help?</p>
                <div className="mt-4 flex flex-wrap justify-center gap-2">
                  {SUGGESTIONS.map((text) => (
                    <button key={text} onClick={() => send(text)}
                      className="rounded-full border border-line bg-surface px-3.5 py-1.5 text-sm hover:border-brand hover:text-brand">
                      {text}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {chat.messages.map((message, i) => (
              <Bubble key={i} message={message} why={message.turnId ? whys[message.turnId] : undefined}
                onTrace={loadTrace} onWhy={toggleWhy} onCite={(citation) => setPanel({ kind: "citation", citation })}
                onAction={(id) => id === "talk_to_human" && send("I'd like to talk to a person, please.")} />
            ))}
            {chat.draft && <div className="max-w-[85%] rounded-2xl border border-line bg-surface p-4 opacity-70">{chat.draft}</div>}
            <div aria-live="polite" className="min-h-6">
              {chat.status && (
                <p className="flex items-center gap-2 text-sm text-muted">
                  <span className="flex gap-1" aria-hidden="true">
                    {["[animation-delay:0ms]", "[animation-delay:150ms]", "[animation-delay:300ms]"].map((delay) => (
                      <span key={delay} className={`size-1.5 animate-pulse rounded-full bg-brand ${delay}`} />
                    ))}
                  </span>
                  {chat.status}
                </p>
              )}
            </div>
            {(chat.error || lost) && (
              <div role="alert" className="flex items-center gap-3 rounded-lg border border-bad/40 bg-bad-soft px-4 py-3 text-sm text-bad">
                <span className="flex-1">{lost ? "Disconnected from the conversation." : chat.error}</span>
                {lost && <button onClick={() => fresh().catch(() => setLost(true))} className="font-medium underline">Start again</button>}
              </div>
            )}
          </div>
        </div>

        <form onSubmit={submit} className="mx-4 mb-4 rounded-2xl border border-line bg-surface p-3 shadow-sm sm:mx-6">
          <label htmlFor="composer" className="sr-only">Message</label>
          <textarea id="composer" rows={2} maxLength={LIMIT} value={input} onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKey} placeholder="Type your message…"
            className="block w-full resize-none bg-transparent px-1 py-1 text-[15px] placeholder:text-muted focus:outline-none" />
          <div className="mt-2 flex items-center justify-between">
            <span className="font-mono text-xs text-muted">{input.length} / {LIMIT}</span>
            <button disabled={sending || !input.trim() || !conversationId}
              className="flex items-center gap-2 rounded-xl bg-brand px-5 py-2.5 font-medium text-white hover:bg-brand-strong disabled:opacity-50">
              <Icon name="send" className="size-4" /> {sending ? "Sending" : "Send"}
            </button>
          </div>
        </form>
      </main>

      {panel?.kind === "trace" && (
        <Drawer title="How this was answered" onClose={() => setPanel(null)}>
          <TraceView item={traces[panel.turnId] ?? { state: "loading" }} retry={() => loadTrace(panel.turnId)} />
        </Drawer>
      )}
      {panel?.kind === "citation" && (
        <Drawer title={panel.citation.title ?? "Source"} icon="doc" onClose={() => setPanel(null)}>
          <CitationView key={panel.citation.doc_id} citation={panel.citation} />
        </Drawer>
      )}
    </div>
  );
}

function Bubble({ message, why, onTrace, onWhy, onCite, onAction }: {
  message: Message;
  why?: Loadable<Why[]>;
  onTrace: (turnId: string) => void;
  onWhy: (turnId: string) => void;
  onCite: (citation: Citation) => void;
  onAction: (id: string) => void;
}) {
  const [copied, setCopied] = useState(false);
  if (message.role === "user") {
    return (
      <div className="ml-auto max-w-[85%] rounded-2xl bg-user px-4 py-3 text-white sm:max-w-[70%]">
        <p className="whitespace-pre-wrap break-words">{message.text}</p>
        <p className="mt-1 flex items-center justify-end gap-1 text-xs text-white/70">
          {clock(message.at)} <Icon name="check" className="size-3.5" />
        </p>
      </div>
    );
  }
  if (message.role !== "assistant") {
    return (
      <p className="mx-auto flex items-center gap-2 rounded-full bg-subtle px-4 py-2 text-sm text-muted">
        <Icon name={message.role === "card" ? "doc" : "person"} className="size-4" /> {message.text}
      </p>
    );
  }
  const citations = message.citations ?? [];
  const actions = (message.actions ?? []).filter((action) => action.id !== "talk_to_human");
  const human = (message.actions ?? []).some((action) => action.id === "talk_to_human");
  const link = "flex items-center gap-1.5 rounded-md px-2 py-1 text-sm text-muted hover:bg-subtle hover:text-ink";
  const action = (icon: IconName, label: string, onClick: () => void, active = false) => (
    <button onClick={onClick} className={`${link} ${active ? "text-brand" : ""}`} aria-pressed={active}>
      <Icon name={icon} className="size-4" /> {label}
    </button>
  );
  return (
    <article className="max-w-full sm:max-w-[85%]">
      <div className="rounded-2xl border border-line bg-surface p-4 shadow-sm">
        <span className="mb-2 inline-block rounded-full bg-brand px-2.5 py-0.5 text-xs font-medium text-white">AI-assisted</span>
        <p className="whitespace-pre-wrap break-words leading-relaxed">{message.text}</p>
        <p className="mt-2 text-right text-xs text-muted">{clock(message.at)}</p>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-1">
        {citations.length > 0 && action("sources", `Sources (${citations.length})`, () => onCite(citations[0]))}
        {message.turnId && action("external", "How this was answered", () => onTrace(message.turnId!))}
        {message.turnId && action("why", "Why this answer", () => onWhy(message.turnId!), Boolean(why))}
        <button onClick={() => navigator.clipboard?.writeText(message.text).then(() => setCopied(true))}
          className={link} aria-label="Copy reply">
          <Icon name={copied ? "check" : "copy"} className="size-4" />
        </button>
      </div>
      {citations.length > 0 && (
        <ul className="mt-2 flex flex-wrap gap-2" aria-label="Sources">
          {citations.map((citation, i) => (
            <li key={`${citation.doc_id}-${i}`}>
              <button onClick={() => onCite(citation)}
                className="flex items-center gap-2 rounded-lg border border-line bg-surface px-3 py-1.5 text-sm hover:border-brand">
                <span className="grid size-5 place-items-center rounded bg-brand text-[11px] font-semibold text-white">{i + 1}</span>
                <Icon name="doc" className="size-4 text-muted" />
                <span className="max-w-[16rem] truncate">{citation.title ?? citation.doc_id}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {(human || actions.length > 0) && (
        <div className="mt-2 flex flex-wrap gap-2">
          {[...actions, ...(human ? [{ id: "talk_to_human", label: "Talk to a human" }] : [])].map((item) => (
            <button key={item.id} onClick={() => onAction(item.id)}
              className="flex items-center gap-1.5 rounded-full border border-brand/50 px-3 py-1 text-sm text-brand hover:bg-brand-soft">
              {item.id === "talk_to_human" && <Icon name="person" className="size-4" />} {item.label}
            </button>
          ))}
        </div>
      )}
      {why && message.turnId && <WhyPanel item={why} onClose={() => onWhy(message.turnId!)} />}
    </article>
  );
}
