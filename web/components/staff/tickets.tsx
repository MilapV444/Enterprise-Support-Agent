"use client";
// Staff tickets: every tenant's raised tickets with filters, sorting, pages and bulk close / reject, and one
// ticket's page with its moves (hitl.tickets.MOVES), refund approval, replies, internal notes and history.
import Link from "next/link";
import { useMemo, useState, type ReactNode } from "react";

import {
  ACTIVE, NO_FILTER, STATUSES, actorLabel, canMove, didWhat, customerHref, filterTickets, movesFor, optionsOf, paginate,
  sortTickets, staffApi, ticketHref, type Move, type StaffTicket, type TicketFilter, type TicketSort,
} from "@/lib/staff.ts";
import { money, statusLabel } from "@/lib/tickets.ts";
import { ago } from "@/lib/services.ts";
import {
  Button, Empty, Loading, PageTitle, Problem, Search, Select, TicketStatus, category, input, panel, queue, td, th,
  useLoad, when,
} from "./ui.tsx";

const all = (label: string, values: string[], show: (v: string) => string = (v) => v): [string, string][] =>
  [["all", label], ...values.map((v): [string, string] => [v, show(v)])];

export function TicketsTable({ tickets, selected, onSelect }: {
  tickets: StaffTicket[]; selected?: Set<string>; onSelect?: (id: string, on: boolean) => void;
}) {
  return (
    <div className={`${panel} overflow-x-auto`}>
      <table className="w-full min-w-[760px] text-sm">
        <thead className="border-b border-slate-200 dark:border-slate-800">
          <tr>
            {onSelect && <th className={th}><span className="sr-only">Select</span></th>}
            <th className={th}>Ticket</th><th className={th}>Customer</th><th className={th}>Subject</th>
            <th className={th}>Team</th><th className={th}>Amount</th><th className={th}>Status</th><th className={th}>Age</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
          {tickets.map((t) => (
            <tr key={t.ticket_id} className="hover:bg-slate-50 dark:hover:bg-slate-800/50">
              {onSelect && (
                <td className={td}>
                  <input type="checkbox" aria-label={`Select ${t.ticket_id}`} checked={selected?.has(t.ticket_id) ?? false}
                    onChange={(e) => onSelect(t.ticket_id, e.target.checked)} className="size-4 accent-indigo-600" />
                </td>
              )}
              <td className={td}>
                <Link href={ticketHref(t.ticket_id)} className="font-mono font-medium text-indigo-700 hover:underline dark:text-indigo-300">{t.ticket_id}</Link>
                <span className="block text-xs text-slate-500">{category(t.category)}</span>
              </td>
              <td className={td}>
                <Link href={customerHref(t.tenant_id, t.principal_id)} className="hover:underline">{t.principal_id}</Link>
                <span className="block text-xs text-slate-500">{t.tenant_id}</span>
              </td>
              <td className={`${td} max-w-xs`}><span className="line-clamp-2">{t.subject}</span></td>
              <td className={`${td} whitespace-nowrap`}>{queue(t.queue)}</td>
              <td className={`${td} whitespace-nowrap tabular-nums`}>{money(t.amount_cents, t.currency) ?? "—"}</td>
              <td className={td}><TicketStatus status={t.status} /></td>
              <td className={`${td} whitespace-nowrap text-slate-500`} title={when(t.created_at)}>{ago(t.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function TicketsView() {
  const { data, error, reload } = useLoad("tickets", staffApi.tickets);
  const [filter, setFilter] = useState<TicketFilter>({ ...NO_FILTER, status: "active" });
  const [sort, setSort] = useState<TicketSort>("newest");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [reason, setReason] = useState("");
  const [bulk, setBulk] = useState<string | null>(null);
  const shown = useMemo(() => sortTickets(filterTickets(data ?? [], filter), sort), [data, filter, sort]);
  const { items, page: current, pages } = paginate(shown, page);
  const set = (patch: Partial<TicketFilter>) => { setFilter((f) => ({ ...f, ...patch })); setPage(1); setSelected(new Set()); };
  const picked = (data ?? []).filter((t) => selected.has(t.ticket_id));

  async function applyAll(to: "closed" | "rejected") {
    const able = picked.filter((t) => canMove(t, to));
    const results = await Promise.allSettled(able.map((t) => staffApi.move(t.ticket_id, to, reason)));
    const failed = results.filter((r) => r.status === "rejected").length + (picked.length - able.length);
    setBulk(`${statusLabel(to)}: ${results.length - results.filter((r) => r.status === "rejected").length} of ${picked.length}`
      + (failed ? ` (${failed} could not be ${to === "closed" ? "closed" : "rejected"} from their status)` : ""));
    setSelected(new Set()); setReason(""); reload();
  }

  if (!data) return <><PageTitle title="Tickets" /><Loading error={error} /></>;
  return (
    <>
      <PageTitle title="Tickets" sub={`${shown.length} of ${data.length} tickets`}>
        <Button onClick={reload}>Refresh</Button>
      </PageTitle>
      <div className={`${panel} mb-4 flex flex-wrap items-end gap-3 p-3`}>
        <Search value={filter.q} onChange={(q) => set({ q })} placeholder="Ticket, email, subject or invoice" />
        <Select label="Status" value={filter.status} onChange={(status) => set({ status: status as TicketFilter["status"] })}
          options={[["active", "Open + in review"], ["all", "All statuses"], ...STATUSES.map((s): [string, string] => [s, statusLabel(s)])]} />
        <Select label="Category" value={filter.category} onChange={(c) => set({ category: c })}
          options={all("All categories", optionsOf(data, (t) => t.category), category)} />
        <Select label="Team" value={filter.queue} onChange={(q) => set({ queue: q })}
          options={all("All teams", optionsOf(data, (t) => t.queue), queue)} />
        <Select label="Tenant" value={filter.tenant} onChange={(t) => set({ tenant: t })}
          options={all("All tenants", optionsOf(data, (t) => t.tenant_id))} />
        <label className="flex flex-col gap-1 text-xs font-medium text-slate-500">From
          <input type="date" value={filter.from} onChange={(e) => set({ from: e.target.value })} className={input} /></label>
        <label className="flex flex-col gap-1 text-xs font-medium text-slate-500">To
          <input type="date" value={filter.to} onChange={(e) => set({ to: e.target.value })} className={input} /></label>
        <Select label="Sort" value={sort} onChange={(s) => setSort(s as TicketSort)}
          options={[["newest", "Newest first"], ["oldest", "Oldest first"], ["updated", "Recently updated"], ["amount", "Largest amount"]]} />
        <Button onClick={() => { setFilter(NO_FILTER); setPage(1); }}>Clear</Button>
      </div>
      {selected.size > 0 && (
        <div className="mb-3 flex flex-wrap items-center gap-2 rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-2 text-sm dark:border-indigo-900 dark:bg-indigo-950">
          <span className="font-medium">{selected.size} selected</span>
          <Button onClick={() => applyAll("closed")}>Close</Button>
          <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reason to reject"
            aria-label="Reason to reject" className={`${input} min-w-56 flex-1`} />
          <Button tone="danger" disabled={!reason.trim()} onClick={() => applyAll("rejected")}>Reject</Button>
          <Button onClick={() => setSelected(new Set())}>Clear selection</Button>
        </div>
      )}
      {bulk && <p role="status" className="mb-3 text-sm text-slate-600 dark:text-slate-300">{bulk}</p>}
      {items.length === 0
        ? <Empty title="No tickets match">Clear the filters, or raise one from the customer portal&apos;s chat.</Empty>
        : <TicketsTable tickets={items} selected={selected}
            onSelect={(id, on) => setSelected((s) => { const next = new Set(s); if (on) next.add(id); else next.delete(id); return next; })} />}
      {pages > 1 && (
        <nav aria-label="Pages" className="mt-3 flex items-center justify-end gap-2 text-sm">
          <Button disabled={current === 1} onClick={() => setPage(current - 1)}>Previous</Button>
          <span>Page {current} of {pages}</span>
          <Button disabled={current === pages} onClick={() => setPage(current + 1)}>Next</Button>
        </nav>
      )}
    </>
  );
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return <div><dt className="text-xs text-slate-500 dark:text-slate-400">{label}</dt><dd className="mt-0.5 break-words text-sm">{children}</dd></div>;
}

export function TicketView({ ticketId }: { ticketId: string }) {
  const { data, error, reload } = useLoad(`ticket:${ticketId}`, () => staffApi.ticket(ticketId));
  const [ticket, setTicket] = useState<StaffTicket | null>(null);
  const [reason, setReason] = useState("");
  const [text, setText] = useState("");
  const [visibility, setVisibility] = useState<"customer" | "internal">("customer");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const shown = ticket ?? data;

  async function run(work: () => Promise<StaffTicket>) {
    setBusy(true); setProblem(null);
    try { setTicket(await work()); return true; } catch (e) { setProblem((e as Error).message); reload(); return false; } finally { setBusy(false); }
  }
  async function move(m: Move) {
    if (await run(() => staffApi.move(ticketId, m.to, reason, m.credit))) setReason("");
  }
  async function send() {
    if (await run(() => staffApi.note(ticketId, text, visibility))) setText("");
  }

  if (!shown) return <><PageTitle title={ticketId} /><Loading error={error} /></>;
  const moves = movesFor(shown);
  const refund = shown.category === "refund" && shown.invoice_id;
  return (
    <>
      <Link href="/staffs/tickets" className="text-sm text-indigo-700 hover:underline dark:text-indigo-300">← All tickets</Link>
      <PageTitle title={`${shown.ticket_id} · ${shown.subject}`}
        sub={<>{category(shown.category)} · {queue(shown.queue)} · opened {when(shown.opened_at)}</>}>
        <TicketStatus status={shown.status} />
      </PageTitle>
      {problem && <div className="mb-4"><Problem>{problem}</Problem></div>}
      <div className="grid gap-5 lg:grid-cols-[1fr_340px]">
        <div className="space-y-5">
          <section className={`${panel} p-4`} aria-label="Actions">
            <h2 className="mb-3 text-sm font-semibold">Actions</h2>
            {moves.length === 0 ? <p className="text-sm text-slate-500">A closed ticket is final.</p> : (
              <>
                <div className="flex flex-wrap gap-2">
                  {moves.map((m) => (
                    <Button key={m.label} tone={m.tone} disabled={busy || (m.needsReason && !reason.trim())} onClick={() => move(m)}>{m.label}</Button>
                  ))}
                </div>
                <label className="mt-3 block text-xs font-medium text-slate-500">
                  Reason (required to reject; shown to the customer with the status)
                  <input value={reason} onChange={(e) => setReason(e.target.value)} className={`${input} mt-1 w-full`} maxLength={2000} />
                </label>
                {refund && ACTIVE.includes(shown.status) && (
                  <p className="mt-2 text-xs text-slate-500">Approve refund resolves the ticket and marks {shown.invoice_id} credited ({money(shown.amount_cents, shown.currency)}).</p>
                )}
              </>
            )}
          </section>
          <section className={`${panel} p-4`} aria-label="Reply">
            <div className="mb-2 flex items-center gap-1" role="radiogroup" aria-label="Who sees it">
              {(["customer", "internal"] as const).map((v) => (
                <button key={v} role="radio" aria-checked={visibility === v} onClick={() => setVisibility(v)}
                  className={`rounded-md px-3 py-1 text-sm font-medium ${visibility === v
                    ? v === "internal" ? "bg-amber-100 text-amber-900 dark:bg-amber-900 dark:text-amber-100" : "bg-indigo-100 text-indigo-900 dark:bg-indigo-900 dark:text-indigo-100"
                    : "text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"}`}>
                  {v === "customer" ? "Reply to customer" : "Internal note"}
                </button>
              ))}
            </div>
            <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} maxLength={4000}
              aria-label={visibility === "customer" ? "Reply to customer" : "Internal note"}
              placeholder={visibility === "customer" ? "The customer sees this on their ticket." : "Only staff see this."}
              className={`${input} w-full ${visibility === "internal" ? "bg-amber-50 dark:bg-amber-950/40" : ""}`} />
            <div className="mt-2 flex justify-end">
              <Button tone="primary" disabled={busy || !text.trim()} onClick={send}>{visibility === "customer" ? "Send reply" : "Add note"}</Button>
            </div>
          </section>
          <section aria-label="History">
            <h2 className="mb-3 text-sm font-semibold">History</h2>
            <ol className="space-y-3">
              {[...(shown.events ?? [])].reverse().map((e, i) => (
                <li key={i} className={`${panel} px-4 py-3 ${e.visibility === "internal" ? "border-amber-300 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/40" : ""}`}>
                  <p className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
                    <span className="font-semibold text-slate-700 dark:text-slate-200">{actorLabel(e.actor)}</span>
                    <span>{didWhat(e)}</span>
                    {e.visibility === "internal" && <span className="rounded bg-amber-200 px-1.5 text-amber-900 dark:bg-amber-800 dark:text-amber-100">Internal</span>}
                    <span className="ml-auto">{when(e.at)}</span>
                  </p>
                  {e.text && <p className="mt-1 whitespace-pre-wrap break-words text-sm">{e.text}</p>}
                </li>
              ))}
            </ol>
          </section>
        </div>
        <aside className={`${panel} h-fit p-4`}>
          <dl className="grid gap-3">
            <Fact label="Customer"><Link href={customerHref(shown.tenant_id, shown.principal_id)} className="text-indigo-700 hover:underline dark:text-indigo-300">{shown.principal_id}</Link></Fact>
            <Fact label="Tenant">{shown.tenant_id}</Fact>
            <Fact label="Invoice">{shown.invoice_id ?? "—"}</Fact>
            <Fact label="Amount">{money(shown.amount_cents, shown.currency) ?? "—"}</Fact>
            <Fact label="Why it was raised">{shown.reason}</Fact>
            <Fact label="Customer's words (PII as tokens)">{shown.description || "—"}</Fact>
            <Fact label="Conversation"><span className="font-mono text-xs">{shown.conversation_id}</span></Fact>
            <Fact label="Created">{when(shown.created_at)}</Fact>
            <Fact label="Last update">{when(shown.updated_at)}</Fact>
          </dl>
        </aside>
      </div>
    </>
  );
}
