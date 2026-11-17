import Portal from "@/components/portal.tsx";

// One ticket with its history (GET /v1/tickets/{id}); a ticket card in the chat links here.
export default async function TenantTicket({ params }: { params: Promise<{ tenantId: string; ticketId: string }> }) {
  const { tenantId, ticketId } = await params;
  return <Portal tenantId={decodeURIComponent(tenantId)} view="tickets" ticketId={decodeURIComponent(ticketId)} />;
}
