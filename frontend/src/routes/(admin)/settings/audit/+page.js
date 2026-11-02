import { redirect } from "@sveltejs/kit";
import { nutzer } from "$lib/zugang.js";

export async function load() {
  const $user = await nutzer();
  if (!$user?.roles.includes("admin")) {
    redirect(302, "/");
  }
  return {
    title: "Audit-Log",
    headerColor: "bg-light-re dark:bg-dark-re",
    headerTextColor: "text-dark-tx dark:text-light-tx-1",
    sidebarSection: "settings",
  };
}
