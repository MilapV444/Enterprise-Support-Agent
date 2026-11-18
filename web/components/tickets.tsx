"use client";
// Support tickets in the portal (FR-47): the cards a ticket proposal, a raised ticket and the guest's sign-in
// prompt show in the chat, the My tickets list and one ticket's page with its history.
import Link from "next/link";
import { useEffect, useState } from "react";

import { HttpError, type ChatClient } from "@/lib/chat-client.ts";
import {
  categoryLabel, eventText, eventTitle, money, proposalOf, statusLabel, teamLabel, ticketPath, ticketsPath,
  type Ticket, type TicketCard, type TicketDetail,
} from "@/lib/tickets.ts";
import { Icon } from "./icons.tsx";
import type { Loadable } from "./panels.tsx";

const when = (at: string | null | undefined) =>
  at ? new Date(at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "";

export function StatusChip({ status }: { status: string }) {
  const tone = status === "proposed" || status === "expired" ? "border-line text-muted"
    : status === "resolved" || status === "closed" ? "border-ok/40 text-ok"
    : status === "rejected" ? "border-bad/40 text-bad"
    : "border-brand/50 text-brand";
  return <span className={`rounded-full border px-2 py-0.5 text-xs font-medium ${tone}`}>{statusLabel(status)}</span>;
}

function Facts({ ticket, more = [] }: { ticket: Partial<Ticket>; more?: [string, string | null | undefined][] }) {
  const rows: [string, string | null | undefined][] = [
    ["Category", ticket.category && categoryLabel(ticket.category)],
    ["Invoice", ticket.invoice_id],
    ["Amount", money(ticket.amount_cents, ticket.currency)],
    ["Team", ticket.queue && teamLabel(ticket.queue)],
    ...more,
  ];
  return (
    <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
      {rows.filter(([, value]) => value).map(([label, value]) => (
        <div key={label} className="contents">
          <dt className="text-muted">{label}</dt>
          <dd className="font-medium">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

// A card in the conversation. onRaise(proposal) posts the confirmation; the raised ticket's card arrives on the
// event stream. onSignIn takes the customer to the email code sign-in.
export function TicketCardView({ card, tenantId, onRaise, onSignIn }: {
  card: TicketCard;
  tenantId: string;
  onRaise: (proposal: string) => Promise<void>;
  onSignIn: () => void;
}) {
  const [raise, setRaise] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const proposal = proposalOf(card);

  if (card.kind === "sign_in") {
    return (
      <div className="max-w-full rounded-2xl border border-brand/40 bg-brand-soft p-4 sm:max-w-[85%]">
        <p className="flex items-center gap-2 font-medium"><Icon name="mail" className="size-5 text-brand" /> {card.title}</p>
        <p className="mt-1 text-sm text-muted">This belongs to your account, so we need to know who you are first.</p>
        <button onClick={onSignIn} className="mt-3 rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white hover:bg-brand-strong">
          {card.actions?.[0]?.label ?? "Sign in with your email"}
        </button>
      </div>
    );
  }

  if (card.kind === "ticket" && card.ticket_id) {
    return (
      <Link href={ticketPath(tenantId, card.ticket_id)} aria-label={`Open ticket ${card.ticket_id}`}
        className="block max-w-full rounded-2xl border border-line bg-surface p-4 shadow-sm hover:border-brand sm:max-w-[85%]">
        <div className="flex items-center gap-2">
          <Icon name="ticket" className="size-5 text-brand" />
          <span className="flex-1 font-medium">{card.title ?? `Ticket ${card.ticket_id}`}</span>
          <StatusChip status={card.status ?? "open"} />
        </div>
        <p className="mt-2 text-sm">{card.subject}</p>
        <Facts ticket={card} />
        <p className="mt-3 flex items-center gap-1 text-sm font-medium text-brand">Open ticket <Icon name="right" className="size-4" /></p>
      </Link>
    );
  }

  async function confirm() {
    if (!proposal) return;
    setRaise("sending");
    try {
      await onRaise(proposal);
      setRaise("sent");
    } catch {
      setRaise("error");
    }
  }

  return (
    <div className="max-w-full rounded-2xl border border-brand/40 bg-surface p-4 shadow-sm sm:max-w-[85%]">
      <div className="flex items-center gap-2">
        <Icon name="ticket" className="size-5 text-brand" />
        <span className="flex-1 font-medium">{card.title ?? "Raise a ticket?"}</span>
        <StatusChip status={card.status ?? "proposed"} />
      </div>
      <p className="mt-2 text-sm">{card.subject}</p>
      <Facts ticket={card} />
      <p className="mt-3 text-xs text-muted">Nothing is raised until you confirm.</p>
      {proposal && (
        <button onClick={confirm} disabled={raise === "sending" || raise === "sent"}
          className="mt-2 flex items-center gap-2 rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white hover:bg-brand-strong disabled:opacity-60">
          <Icon name={raise === "sent" ? "check" : "ticket"} className="size-4" />
          {raise === "sending" ? "Raising…" : raise === "sent" ? "Requested" : proposal && (card.actions?.[0]?.label ?? "Raise ticket")}
        </button>
      )}
      {raise === "error" && <p role="alert" className="mt-2 text-sm text-bad">Could not send that. Try again.</p>}
    </div>
  );
}

function SignInFirst() {
  return (
    <div className="rounded-2xl border border-line bg-surface p-6 text-center">
      <Icon name="ticket" className="mx-auto mb-3 size-8 text-brand" />
      <p className="font-medium">Sign in to see your tickets</p>
      <p className="mt-1 text-sm text-muted">Use the email code on the left. Tickets belong to your account.</p>
    </div>
  );
}

function useLoad<T>(load: (() => Promise<T>) | null, deps: unknown[]): [Loadable<T> | null, () => void] {
  const [item, setItem] = useState<Loadable<T> | null>(null);
  const [round, setRound] = useState(0);
  useEffect(() => {
    if (!load) return;
    let live = true;
    setItem({ state: "loading" });
    load().then((value) => live && setItem({ state: "ready", value }))
      .catch((error) => live && setItem({
        state: "error",
        message: error instanceof HttpError && error.status === 404 ? "No such ticket." : "Could not load your tickets.",
      }));
    return () => { live = false; };
  }, [...deps, round]); // eslint-disable-line react-hooks/exhaustive-deps
  return [item, () => setRound((n) => n + 1)];
}

function Loading({ item, retry }: { item: Loadable<unknown>; retry: () => void }) {
  if (item.state === "loading") return <p className="text-sm text-muted">Loading…</p>;
  if (item.state === "error") {
    return (
      <p role="alert" className="flex items-center gap-3 rounded-lg border border-bad/40 bg-bad-soft px-4 py-3 text-sm text-bad">
        <span className="flex-1">{item.message}</span>
        <button onClick={retry} className="font-medium underline">Try again</button>
      </p>
    );
  }
  return null;
}

export function TicketsView({ client, tenantId, signedIn }: { client: ChatClient | null; tenantId: string; signedIn: boolean }) {
  const [list, retry] = useLoad<Ticket[]>(client && signedIn ? () => client.tickets() : null, [client, signedIn]);
  if (!signedIn) return <SignInFirst />;
  if (!list || list.state !== "ready") return list ? <Loading item={list} retry={retry} /> : null;
  if (list.value.length === 0) {
    return (
      <div className="rounded-2xl border border-line bg-surface p-6 text-center">
        <p className="font-medium">No tickets yet</p>
        <p className="mt-1 text-sm text-muted">When the assistant offers a ticket in the chat, raise it and it shows up here.</p>
      </div>
    );
  }
  return (
    <ul className="divide-y divide-line overflow-hidden rounded-2xl border border-line bg-surface" aria-label="My tickets">
      {list.value.map((ticket) => (
        <li key={ticket.ticket_id}>
          <Link href={ticketPath(tenantId, ticket.ticket_id)} className="flex items-center gap-4 px-4 py-3 hover:bg-subtle">
            <Icon name="ticket" className="size-5 shrink-0 text-brand" />
            <span className="min-w-0 flex-1">
              <span className="block truncate font-medium">{ticket.subject}</span>
              <span className="block text-xs text-muted">
                {ticket.ticket_id} · {teamLabel(ticket.queue)} · {when(ticket.created_at)}
              </span>
            </span>
            <StatusChip status={ticket.status} />
            <Icon name="right" className="size-4 text-muted" />
          </Link>
        </li>
      ))}
    </ul>
  );
}

export function TicketDetailView({ client, tenantId, ticketId, signedIn }: {
  client: ChatClient | null; tenantId: string; ticketId: string; signedIn: boolean;
}) {
  const [item, retry] = useLoad<TicketDetail>(client && signedIn ? () => client.ticket(ticketId) : null,
    [client, signedIn, ticketId]);
  const back = (
    <Link href={ticketsPath(tenantId)} className="mb-4 inline-flex items-center gap-1 text-sm text-muted hover:text-ink">
      <Icon name="right" className="size-4 rotate-180" /> My tickets
    </Link>
  );
  if (!signedIn) return <>{back}<SignInFirst /></>;
  if (!item || item.state !== "ready") return <>{back}{item && <Loading item={item} retry={retry} />}</>;
  const ticket = item.value;
  return (
    <>
      {back}
      <article className="rounded-2xl border border-line bg-surface p-5 shadow-sm">
        <div className="flex flex-wrap items-center gap-3">
          <Icon name="ticket" className="size-6 text-brand" />
          <h2 className="flex-1 text-lg font-semibold">{ticket.ticket_id}</h2>
          <StatusChip status={ticket.status} />
        </div>
        <p className="mt-2">{ticket.subject}</p>
        <Facts ticket={ticket} more={[["Raised", when(ticket.opened_at) || "Not yet"],
          ["Last update", when(ticket.updated_at)], ["Why a ticket", ticket.reason]]} />
        {ticket.description && (
          <div className="mt-4">
            <p className="text-sm text-muted">What you told us</p>
            <p className="mt-1 whitespace-pre-wrap break-words rounded-lg bg-subtle px-3 py-2 text-sm">{ticket.description}</p>
          </div>
        )}
      </article>
      <h3 className="mb-2 mt-6 font-medium">History</h3>
      <ol className="space-y-3 border-l border-line pl-4" aria-label="Ticket history">
        {ticket.events.map((event, i) => (
          <li key={i} className="relative">
            <span className="absolute -left-[21px] top-1.5 size-2.5 rounded-full bg-brand" aria-hidden="true" />
            <p className="text-sm font-medium">{eventTitle(event)}</p>
            <p className="text-xs text-muted">{when(event.at)}</p>
            {eventText(event) && (
              <p className="mt-1 whitespace-pre-wrap break-words text-sm">{eventText(event)}</p>
            )}
          </li>
        ))}
      </ol>
    </>
  );
}
