import { CustomerView } from "@/components/staff/customers.tsx";

export default async function StaffCustomer({ params }: { params: Promise<{ tenantId: string; email: string }> }) {
  const { tenantId, email } = await params;
  return <CustomerView tenantId={decodeURIComponent(tenantId)} email={decodeURIComponent(email)} />;
}
