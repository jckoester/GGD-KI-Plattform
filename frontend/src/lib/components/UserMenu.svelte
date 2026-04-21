<script>
    import { user } from "$lib/stores/user.js";
    import { goto } from "$app/navigation";
    import {
        Shield,
        User,
        LogOut,
        Eye,
        Wallet,
        BarChart2,
    } from "lucide-svelte";
    import { logout } from "$lib/api.js";
    import { onMount } from "svelte";

    export let onClose = () => {};

    let menuRef;

    async function doLogout() {
        await logout();
        sessionStorage.removeItem("display_name");
        localStorage.removeItem("theme");
        goto("/");
        onClose();
    }

    function handleClickOutside(event) {
        if (menuRef && !menuRef.contains(event.target)) {
            onClose();
        }
    }

    onMount(() => {
        const id = setTimeout(() => {
            window.addEventListener("click", handleClickOutside);
        }, 0);
        return () => {
            clearTimeout(id);
            window.removeEventListener("click", handleClickOutside);
        };
    });
</script>

<div
    bind:this={menuRef}
    class="absolute bottom-16 left-0 right-0 mx-3 bg-light-bg dark:bg-dark-ui rounded-md shadow-lg border border-light-ui-3 dark:border-dark-ui-3 py-0 z-50"
>
    <!-- Admin (nur bei admin-Rolle) -->
    {#if $user?.roles.includes("admin")}
        <a
            href="/admin"
            class="flex items-center px-4 py-2 text-sm text-light-tx-2 dark:text-dark-tx-2 hover:bg-light-ui-2 dark:hover:bg-dark-ui-2"
        >
            <Shield class="w-4 h-4 mr-3 text-light-re dark:text-dark-re" />
            Admin
        </a>
    {/if}

    <!-- Review (nur bei review-Rolle) - vorbereitet für später -->
    {#if $user?.roles.includes("review")}
        <a
            href="#"
            class="flex items-center px-4 py-2 text-sm text-light-tx-2 dark:text-dark-tx-2 hover:bg-light-ui dark:hover:bg-dark-ui"
        >
            <Eye class="w-4 h-4 mr-3" />
            Review
        </a>
    {/if}

    <!-- Budget (nur bei budget-Rolle) - vorbereitet für später -->
    {#if $user?.roles.includes("budget")}
        <a
            href="#"
            class="flex items-center px-4 py-2 text-sm text-light-tx-2 dark:text-dark-tx-2 hover:bg-light-ui dark:hover:bg-dark-ui"
        >
            <Wallet class="w-4 h-4 mr-3" />
            Budget
        </a>
    {/if}

    <!-- Statistik (nur bei statistics-Rolle) - vorbereitet für später -->
    {#if $user?.roles.includes("statistics")}
        <a
            href="#"
            class="flex items-center px-4 py-2 text-sm text-light-tx-2 dark:text-dark-tx-2 hover:bg-light-ui dark:hover:bg-dark-ui"
        >
            <BarChart2 class="w-4 h-4 mr-3" />
            Statistik
        </a>
    {/if}

    <!-- Trenner wenn Rollen-Menüs vorhanden -->
    {#if $user?.roles.some( (r) => ["admin", "review", "budget", "statistics"].includes(r), )}
        <div
            class="border-t border-light-ui-3 dark:border-dark-ui-3 my-0"
        ></div>
    {/if}

    <!-- Profil (immer sichtbar) -->
    <a
        href="/profil"
        onclick={onClose}
        class="flex items-center px-4 py-2 text-sm text-light-tx-2 dark:text-dark-tx-2 hover:bg-light-ui-2 dark:hover:bg-dark-ui-2"
    >
        <User class="w-4 h-4 mr-3" />
        Profil
    </a>

    <!-- Trenner -->
    <div class="border-t border-light-ui-3 dark:border-dark-ui-3 my-0"></div>

    <!-- Abmelden (immer sichtbar) -->
    <button
        onclick={doLogout}
        class="w-full flex items-center px-4 py-2 text-sm text-light-re dark:text-dark-re hover:bg-red-100 dark:hover:bg-red-900 dark:hover:bg-dark-ui"
    >
        <LogOut class="w-4 h-4 mr-3" />
        Abmelden
    </button>
</div>
