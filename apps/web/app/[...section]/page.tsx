import { Suspense } from "react";
import { Workspace } from "@/components/workspace";
export default function Page() {
  return (
    <Suspense fallback={<div>Загрузка…</div>}>
      <Workspace />
    </Suspense>
  );
}
