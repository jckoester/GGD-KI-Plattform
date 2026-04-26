import { get } from "svelte/store";
import { redirect } from "@sveltejs/kit";
import { user } from "$lib/stores/user.js";

export function load() {
  const $user = get(user);
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
