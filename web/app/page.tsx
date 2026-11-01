import Portal from "@/components/portal.tsx";

export default function Home() {
  return <Portal tenantId={process.env.NEXT_PUBLIC_DEFAULT_TENANT ?? "t_us"} />;
}
