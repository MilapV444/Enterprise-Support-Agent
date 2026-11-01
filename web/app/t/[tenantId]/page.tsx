import Portal from "@/components/portal.tsx";

// A tenant deep link: /t/t_eu opens the portal for that tenant (the API checks it exists at sign-in).
export default async function TenantChat({ params }: { params: Promise<{ tenantId: string }> }) {
  const { tenantId } = await params;
  return <Portal tenantId={decodeURIComponent(tenantId)} />;
}
