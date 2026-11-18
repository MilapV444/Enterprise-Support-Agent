import { TicketView } from "@/components/staff/tickets.tsx";

export default async function StaffTicket({ params }: { params: Promise<{ ticketId: string }> }) {
  const { ticketId } = await params;
  return <TicketView ticketId={decodeURIComponent(ticketId)} />;
}
