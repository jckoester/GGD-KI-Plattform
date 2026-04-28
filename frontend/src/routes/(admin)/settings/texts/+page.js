import { get } from "svelte/store";
import { redirect } from "@sveltejs/kit";
import { user } from "$lib/stores/user.js";

export function load() {
  const $user = get(user);
  if (!$user?.roles.includes("admin")) {
    redirect(302, "/");
  }
  return {
    title: "Einstellungen",
    headerColor: "bg-light-re dark:bg-dark-re",
    headerTextColor: "text-dark-tx dark:text-light-tx-1",
    sidebarSection: "settings-texts",
  };
}
