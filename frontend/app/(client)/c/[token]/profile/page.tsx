"use client";
import { useParams } from "next/navigation";
import { ClientNav } from "@/components/ClientNav";
import TrainingDashboard from "@/components/TrainingDashboard";
import { ErrorBox, Spinner, useLoad } from "@/components/ui";
import { api } from "@/lib/api";

export default function ClientProfileDashboard() {
  const { token } = useParams<{ token: string }>();
  const { data, error, loading, reload } = useLoad(() => api.activity(token), [token]);
  return (
    <main className="mx-auto max-w-5xl space-y-4 px-4 py-6">
      <ClientNav token={token} current="profile" />
      {loading && !data ? <Spinner /> : error || !data ? <ErrorBox message={error ?? "Not found"} onRetry={reload} /> : <TrainingDashboard a={data} />}
    </main>
  );
}
