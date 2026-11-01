import { redirect } from "@sveltejs/kit";
import { nutzer } from "$lib/zugang.js";

export async function load() {
  const $user = await nutzer();
  if (!$user?.roles.some((r) => ["budget", "admin"].includes(r))) {
    redirect(302, "/");
  }
  return {
    title: "Budget",
    headerColor: "bg-light-ma dark:bg-dark-ma",
    headerTextColor: "text-dark-tx dark:text-light-tx-1",
    sidebarSection: "budget",
  };
}
