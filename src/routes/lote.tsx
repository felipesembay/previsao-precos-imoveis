import { createFileRoute } from "@tanstack/react-router";
import { EmptyState, PageHeader } from "@/components/states";

export const Route = createFileRoute("/lote")({
  head: () => ({
    meta: [
      { title: "Avaliação em lote — Preço Justo" },
      { name: "description", content: "Avaliação em lote na plataforma Preço Justo." },
      { property: "og:title", content: "Avaliação em lote — Preço Justo" },
      { property: "og:description", content: "Avaliação em lote na plataforma Preço Justo." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: () => (
    <>
      <PageHeader title="Avaliação em lote" />
      <EmptyState title="Página em construção">Esta seção será publicada em breve.</EmptyState>
    </>
  ),
});
