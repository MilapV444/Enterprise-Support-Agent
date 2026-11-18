// Support tickets in the portal (FR-47): the card fields the API sends (hitl.tickets.Ticket.card), the detail
// view's extra fields, and the formatting the cards, the list and the detail page share. Pure.

export type TicketStatus = "proposed" | "open" | "in_review" | "resolved" | "closed" | "expired" | "rejected";
export type Ticket = {
  ticket_id: string;            // TKT-00042
  status: TicketStatus;
  category: string;
  subject: string;
  invoice_id: string | null;
  amount_cents: number | null;
  currency: string | null;
  queue: string;
  created_at: string;
};
// visibility only reaches the staff console: the customer's API leaves staff-only notes out entirely.
export type TicketEvent = {
  kind: "proposed" | "confirmed" | "note" | "status"; actor: string; text: string; at: string;
  visibility?: "customer" | "internal";
};
export type TicketDetail = Ticket & {
  description: string;
  reason: string;
  conversation_id: string;
  opened_at: string | null;
  updated_at: string;
  events: TicketEvent[];
};
// An action_card event: a ticket proposal, a raised ticket, or the guest's sign-in prompt.
export type TicketCard = Partial<Ticket> & {
  kind: "ticket_proposal" | "ticket" | "sign_in";
  title?: string;
  actions?: { type: string; proposal?: string; label: string }[];
};

const STATUS: Record<TicketStatus, string> = {
  proposed: "Not raised yet", open: "Open", in_review: "In review", resolved: "Resolved", closed: "Closed",
  expired: "Offer expired", rejected: "Rejected",
};
const TEAMS: Record<string, string> = {
  queue_billing: "Billing team", queue_technical: "Technical team", queue_account: "Account team",
  queue_senior: "Support team",
};
const EVENTS: Record<TicketEvent["kind"], string> = {
  proposed: "Offered by the assistant", confirmed: "Raised", note: "Message added", status: "Status changed",
};

export const statusLabel = (status: string) => STATUS[status as TicketStatus] ?? status;
export const teamLabel = (queue: string) => TEAMS[queue] ?? "Support team";
export const eventLabel = (kind: string) => EVENTS[kind as TicketEvent["kind"]] ?? kind;
export const byStaff = (actor: string) => actor.startsWith("staff:");
// A timeline entry's title: a staff member's note is their reply.
export const eventTitle = (event: TicketEvent) =>
  event.kind === "note" && byStaff(event.actor) ? "Reply from support" : eventLabel(event.kind);
// What a timeline entry shows under its title: a note's text, or why staff changed the status.
export const eventText = (event: TicketEvent) =>
  event.kind === "note" || (event.kind === "status" && byStaff(event.actor)) ? event.text : "";
export const categoryLabel = (category: string) => category.charAt(0).toUpperCase() + category.slice(1);

export function money(cents: number | null | undefined, currency: string | null | undefined) {
  if (cents == null) return null;
  return new Intl.NumberFormat("en-US", { style: "currency", currency: currency || "USD" }).format(cents / 100);
}

export const ticketsPath = (tenantId: string) => `/t/${encodeURIComponent(tenantId)}/tickets`;
export const ticketPath = (tenantId: string, ticketId: string) =>
  `${ticketsPath(tenantId)}/${encodeURIComponent(ticketId)}`;

// The proposal number a card's Raise ticket button confirms, or null when the card has none.
export function proposalOf(card: TicketCard): string | null {
  return card.actions?.find((action) => action.type === "confirm_ticket")?.proposal ?? null;
}
