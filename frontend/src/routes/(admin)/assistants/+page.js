import { get } from "svelte/store";
import { redirect } from "@sveltejs/kit";
import { user } from "$lib/stores/user.js";

export function load() {
  const $user = get(user);
  if (!$user?.roles.includes("admin")) redirect(302, "/");
  return {
    title: "Assistenten",
    headerColor: "bg-light-bl dark:bg-dark-bl",
    headerTextColor: "text-dark-tx dark:text-light-tx-1",
    sidebarSection: "assistants",
  };
}
