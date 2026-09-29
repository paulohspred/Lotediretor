import { ExplorerShell } from "@/components/explorer-shell";
import { requireViewer } from "@/lib/server/viewer";

export const dynamic = "force-dynamic";

export default async function ExplorerPage({
  searchParams,
}: {
  searchParams: Promise<{ lat?: string; lng?: string }>;
}) {
  const viewer = await requireViewer("/explorer");
  const params = await searchParams;
  const lat = Number(params.lat);
  const lng = Number(params.lng);
  const initialPoint =
    Number.isFinite(lat) && Number.isFinite(lng) && Math.abs(lat) <= 90 && Math.abs(lng) <= 180
      ? { lat, lng }
      : null;
  return (
    <ExplorerShell
      initialPoint={initialPoint}
      canSave={viewer.mode === "oidc" && viewer.me.active_org.role !== "VIEWER"}
    />
  );
}
