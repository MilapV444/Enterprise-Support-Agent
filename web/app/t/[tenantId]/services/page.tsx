import Portal from "@/components/portal.tsx";

// Services: the signed-in customer's servers and container apps and their live status (GET /v1/services).
export default async function TenantServices({ params }: { params: Promise<{ tenantId: string }> }) {
  const { tenantId } = await params;
  return <Portal tenantId={decodeURIComponent(tenantId)} view="services" />;
}
