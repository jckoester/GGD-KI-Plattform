import { redirect } from "@sveltejs/kit";
import { nutzer } from "$lib/zugang.js";

export async function load() {
  const $user = await nutzer();
  if (!$user?.roles.some((r) => ["statistics", "admin"].includes(r))) {
    redirect(302, "/");
  }
  return {
    title: "Antwortbewertung",
    headerColor: "bg-light-gr dark:bg-dark-gr",
    headerTextColor: "text-dark-tx dark:text-light-tx-1",
    sidebarSection: "statistics",
  };
}
