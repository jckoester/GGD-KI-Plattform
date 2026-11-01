import { redirect } from "@sveltejs/kit";
import { nutzer } from "$lib/zugang.js";

export async function load() {
  const $user = await nutzer();
  if (!$user?.roles.includes("admin")) {
    redirect(302, "/");
  }
  return {
    title: "Export-Vorlagen",
    sidebarSection: "settings-export",
  };
}
