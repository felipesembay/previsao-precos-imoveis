import { createFileRoute } from "@tanstack/react-router";
import { EmptyState, PageHeader } from "@/components/states";

export const Route = createFileRoute("/mercado")({
  head: () => ({
    meta: [
      { title: "Mercado de aluguel em SP — Preço Justo" },
      { name: "description", content: "Mercado de aluguel em SP na plataforma Preço Justo." },
      { property: "og:title", content: "Mercado de aluguel em SP — Preço Justo" },
      { property: "og:description", content: "Mercado de aluguel em SP na plataforma Preço Justo." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: () => (
    <>
      <PageHeader title="Mercado de aluguel em SP" />
      <EmptyState title="Página em construção">Esta seção será publicada em breve.</EmptyState>
    </>
  ),
});
