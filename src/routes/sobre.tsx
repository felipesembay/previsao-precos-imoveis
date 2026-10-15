import { createFileRoute } from "@tanstack/react-router";
import { EmptyState, PageHeader } from "@/components/states";

export const Route = createFileRoute("/sobre")({
  head: () => ({
    meta: [
      { title: "Sobre o projeto — Preço Justo" },
      { name: "description", content: "Sobre o projeto na plataforma Preço Justo." },
      { property: "og:title", content: "Sobre o projeto — Preço Justo" },
      { property: "og:description", content: "Sobre o projeto na plataforma Preço Justo." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: () => (
    <>
      <PageHeader title="Sobre o projeto" />
      <EmptyState title="Página em construção">Esta seção será publicada em breve.</EmptyState>
    </>
  ),
});
