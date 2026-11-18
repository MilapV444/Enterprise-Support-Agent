// The Services tab: the signed-in customer's servers and container apps (GET /v1/services, tools.services)
// and the chat cards for a service action. Pure.

export type ServiceStatus = "running" | "stopped" | "stopping" | "starting" | "restarting" | "scaling";
export type Service = {
  service_id: string;
  name: string;
  kind: "server" | "app";
  region: string;
  status: ServiceStatus;
  replicas: number | null;
  updated_at: string;
};
export type ServiceActivity = {
  action_id: string;            // ACT-00042
  service: string;
  action: "stop" | "start" | "restart" | "scale";
  replicas: number | null;
  conversation_id: string;
  at: string;
  actor?: string;               // "agent" (a confirmed chat offer) or "staff:..." (the staff console)
  principal_id?: string;        // the staff console's activity names the customer
};
export type Services = { services: Service[]; activity: ServiceActivity[] };
// An action_card event: an offer with its Confirm button, or the service after the change.
export type ServiceCard = {
  kind: "service_action_proposal" | "service";
  title?: string;
  action_id?: string;
  action?: ServiceActivity["action"];
  replicas?: number | null;
  service?: string;
  service_kind?: Service["kind"];
  region?: string;
  status?: string;
  actions?: { type: string; proposal?: string; label: string }[];
};

export const SERVICE_CARDS = new Set(["service_action_proposal", "service"]);
const BUSY = new Set(["stopping", "starting", "restarting", "scaling"]);
const ACTIONS: Record<ServiceActivity["action"], string> = {
  stop: "Stopped", start: "Started", restart: "Restarted", scale: "Scaled",
};

export const servicesPath = (tenantId: string) => `/t/${encodeURIComponent(tenantId)}/services`;
export const statusLabel = (status: string) => status.charAt(0).toUpperCase() + status.slice(1);
export const busy = (status: string) => BUSY.has(status);
// "good" running, "busy" while a change settles, "idle" stopped
export const tone = (status: string) => status === "running" ? "good" : busy(status) ? "busy" : "idle";
export const kindLabel = (kind: string) => kind === "app" ? "Container app" : "Server";
// Who carried a change out, as the customer reads it.
export const doneBy = (entry: ServiceActivity) =>
  entry.actor?.startsWith("staff:") ? "Support staff" : "Support assistant";

export function activityLabel(entry: ServiceActivity) {
  const scale = entry.action === "scale" && entry.replicas ? ` to ${entry.replicas} replicas` : "";
  return `${ACTIONS[entry.action] ?? entry.action} ${entry.service}${scale}`;
}

// The latest thing the assistant did on each service, by name.
export function lastAction(activity: ServiceActivity[]): Record<string, ServiceActivity> {
  const latest: Record<string, ServiceActivity> = {};
  for (const entry of activity) latest[entry.service] ??= entry;  // the API sends newest first
  return latest;
}

// The offer number a card's Confirm button carries out, or null when the card has none.
export function offerOf(card: ServiceCard): string | null {
  return card.actions?.find((action) => action.type === "confirm_action")?.proposal ?? null;
}

export function ago(at: string, now = Date.now()) {
  const seconds = Math.max(0, Math.round((now - new Date(at).getTime()) / 1000));
  if (seconds < 45) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  return hours < 24 ? `${hours} h ago` : new Date(at).toLocaleDateString();
}
