import Portal from "@/components/portal.tsx";

// My tickets: the signed-in customer's raised tickets (GET /v1/tickets).
export default async function TenantTickets({ params }: { params: Promise<{ tenantId: string }> }) {
  const { tenantId } = await params;
  return <Portal tenantId={decodeURIComponent(tenantId)} view="tickets" />;
}
