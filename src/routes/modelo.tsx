import { createFileRoute } from "@tanstack/react-router";
import { EmptyState, PageHeader } from "@/components/states";

export const Route = createFileRoute("/modelo")({
  head: () => ({
    meta: [
      { title: "Modelo em produção — Preço Justo" },
      { name: "description", content: "Modelo em produção na plataforma Preço Justo." },
      { property: "og:title", content: "Modelo em produção — Preço Justo" },
      { property: "og:description", content: "Modelo em produção na plataforma Preço Justo." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: () => (
    <>
      <PageHeader title="Modelo em produção" />
      <EmptyState title="Página em construção">Esta seção será publicada em breve.</EmptyState>
    </>
  ),
});
