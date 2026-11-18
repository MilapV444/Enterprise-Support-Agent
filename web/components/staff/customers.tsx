"use client";
// Staff customers: everyone with an account, a ticket, a service or a sign-in, with their sign-in status,
// tickets and service health; and one customer's account, invoices, tickets, services and activity.
import Link from "next/link";
import { useMemo, useState } from "react";

import {
  NO_CUSTOMER_FILTER, customerHref, filterCustomers, optionsOf, serviceHealth, staffApi, type CustomerFilter,
} from "@/lib/staff.ts";
import { activityLabel, ago, doneBy } from "@/lib/services.ts";
import { ServicesTable } from "./services.tsx";
import { TicketsTable } from "./tickets.tsx";
import { Button, Empty, Loading, PageTitle, Search, Select, panel, td, th, useLoad, when } from "./ui.tsx";

function Presence({ online, lastSeen }: { online: boolean; lastSeen: string | null }) {
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap text-xs">
      <span className={`size-2 rounded-full ${online ? "bg-emerald-500" : "bg-slate-300 dark:bg-slate-600"}`} aria-hidden="true" />
      {online ? "Online" : lastSeen ? `Seen ${ago(lastSeen)}` : "Never signed in"}
    </span>
  );
}

export function CustomersView() {
  const people = useLoad("customers", staffApi.customers);
  const services = useLoad("services", staffApi.services);
  const [filter, setFilter] = useState<CustomerFilter>(NO_CUSTOMER_FILTER);
  const shown = useMemo(() => filterCustomers(people.data ?? [], filter), [people.data, filter]);
  const set = (patch: Partial<CustomerFilter>) => setFilter((f) => ({ ...f, ...patch }));
  const reload = () => { people.reload(); services.reload(); };

  if (!people.data) return <><PageTitle title="Customers" /><Loading error={people.error} /></>;
  const opts = (label: string, values: string[]): [string, string][] => [["all", label], ...values.map((v): [string, string] => [v, v])];
  return (
    <>
      <PageTitle title="Customers" sub={`${shown.length} of ${people.data.length} customers · ${people.data.filter((c) => c.online).length} online now`}>
        <Button onClick={reload}>Refresh</Button>
      </PageTitle>
      <div className={`${panel} mb-4 flex flex-wrap items-end gap-3 p-3`}>
        <Search value={filter.q} onChange={(q) => set({ q })} placeholder="Email or company" />
        <Select label="Tenant" value={filter.tenant} onChange={(tenant) => set({ tenant })} options={opts("All tenants", optionsOf(people.data, (c) => c.tenant_id))} />
        <Select label="Plan" value={filter.plan} onChange={(plan) => set({ plan })} options={opts("All plans", optionsOf(people.data, (c) => c.plan))} />
        <label className="flex items-center gap-2 pb-1.5 text-sm">
          <input type="checkbox" checked={filter.openOnly} onChange={(e) => set({ openOnly: e.target.checked })} className="size-4 accent-indigo-600" />
          Has open tickets
        </label>
      </div>
      {shown.length === 0 ? <Empty title="No customers match" /> : (
        <div className={`${panel} overflow-x-auto`}>
          <table className="w-full min-w-[760px] text-sm">
            <thead className="border-b border-slate-200 dark:border-slate-800">
              <tr><th className={th}>Customer</th><th className={th}>Company</th><th className={th}>Plan</th>
                <th className={th}>Sign-in</th><th className={th}>Tickets</th><th className={th}>Services</th></tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {shown.map((c) => {
                const health = serviceHealth((services.data ?? []).filter((s) => s.tenant_id === c.tenant_id && s.principal_id === c.principal_id));
                return (
                  <tr key={`${c.tenant_id}/${c.principal_id}`} className="hover:bg-slate-50 dark:hover:bg-slate-800/50">
                    <td className={td}>
                      <Link href={customerHref(c.tenant_id, c.principal_id)} className="font-medium text-indigo-700 hover:underline dark:text-indigo-300">{c.principal_id}</Link>
                      <span className="block text-xs text-slate-500">{c.tenant_id}{c.region && ` · ${c.region}`}</span>
                    </td>
                    <td className={td}>{c.company ?? "—"}</td>
                    <td className={td}>{c.plan ?? "—"}</td>
                    <td className={td}><Presence online={c.online} lastSeen={c.last_seen} /></td>
                    <td className={`${td} tabular-nums`}>{c.open_tickets} open <span className="text-slate-500">/ {c.tickets}</span></td>
                    <td className={`${td} text-xs`}>
                      {health.running + health.busy + health.stopped === 0 ? "—" : (
                        <span className="flex flex-wrap gap-x-3">
                          <span>{health.running} running</span>
                          {health.busy > 0 && <span className="text-amber-700 dark:text-amber-300">{health.busy} changing</span>}
                          {health.stopped > 0 && <span className="text-slate-500">{health.stopped} stopped</span>}
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

export function CustomerView({ tenantId, email }: { tenantId: string; email: string }) {
  const { data, error, reload } = useLoad(`customer:${tenantId}/${email}`, () => staffApi.customer(tenantId, email), 10_000);
  if (!data) return <><PageTitle title={email} /><Loading error={error} /></>;
  const services = data.services.map((s) => ({ ...s, tenant_id: data.tenant_id, principal_id: data.principal_id }));
  return (
    <>
      <Link href="/staffs/customers" className="text-sm text-indigo-700 hover:underline dark:text-indigo-300">← All customers</Link>
      <PageTitle title={email} sub={data.account ? `${data.account.company} · ${data.account.plan} plan · ${data.account.region} · customer since ${data.account.since}` : data.tenant_id} />
      <div className="grid gap-5 lg:grid-cols-2">
        <section aria-label="Invoices">
          <h2 className="mb-2 text-sm font-semibold">Invoices</h2>
          {data.invoices.length === 0 ? <Empty title="No invoices" /> : (
            <div className={`${panel} overflow-x-auto`}>
              <table className="w-full text-sm">
                <thead className="border-b border-slate-200 dark:border-slate-800"><tr><th className={th}>Invoice</th><th className={th}>Issued</th><th className={th}>Amount</th><th className={th}>Status</th></tr></thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                  {data.invoices.map((i) => (
                    <tr key={i.invoice_id}>
                      <td className={`${td} font-mono`}>{i.invoice_id}</td><td className={td}>{i.issued_on}</td>
                      <td className={`${td} tabular-nums`}>{new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(i.amount_usd)}</td>
                      <td className={td}><span className={i.status.includes("credited") ? "font-medium text-emerald-700 dark:text-emerald-300" : ""}>{i.status}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
        <section aria-label="Activity">
          <h2 className="mb-2 text-sm font-semibold">Service activity</h2>
          {data.activity.length === 0 ? <Empty title="Nothing done on their services yet" /> : (
            <ol className={`${panel} divide-y divide-slate-100 dark:divide-slate-800`}>
              {data.activity.map((a) => (
                <li key={a.action_id} className="flex flex-wrap justify-between gap-2 px-4 py-2.5 text-sm">
                  <span>{activityLabel(a)} <span className="text-slate-500">· {doneBy(a)}</span></span>
                  <span className="text-xs text-slate-500">{when(a.at)}</span>
                </li>
              ))}
            </ol>
          )}
        </section>
      </div>
      <h2 className="mb-2 mt-6 text-sm font-semibold">Tickets</h2>
      {data.tickets.length === 0 ? <Empty title="No tickets raised" /> : <TicketsTable tickets={data.tickets} />}
      <h2 className="mb-2 mt-6 text-sm font-semibold">Services</h2>
      {services.length === 0 ? <Empty title="No services" /> : <ServicesTable services={services} onChanged={reload} showCustomer={false} />}
    </>
  );
}
