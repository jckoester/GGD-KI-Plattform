<script>
    import { user } from "$lib/stores/user.js";
    import { Coins, HelpCircle, Info, AlertTriangle } from "lucide-svelte";
    import UserMenu from "./UserMenu.svelte";

    let menuOpen = $state(false);

    function getInitials(name) {
        if (!name) return "??";
        const parts = name.trim().split(/\s+/);
        if (parts.length === 1) {
            return parts[0].slice(0, 2).toUpperCase();
        }
        return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
    }

    function toggleMenu() {
        menuOpen = !menuOpen;
    }

    function closeMenu() {
        menuOpen = false;
    }
</script>

<div
    class="pb-0 p-3 border-t border-light-ui-3 dark:border-dark-ui-3 flex-shrink-0"
>
    <!-- Budget-Zeile -->
    <div class="flex items-center text-xs mb-3">
        <Coins class="w-3 h-3 mr-2 text-light-tx-2 dark:text-dark-tx-2" />
        <span class="text-light-tx-2 dark:text-dark-tx-2">–/– €</span>
        <span class="ml-auto text-xs text-light-tx-3 dark:text-dark-tx-3"
            >r: –</span
        >
    </div>

    <!-- Benutzerbereich -->
    <div class="relative">
        <button
            onclick={toggleMenu}
            class="w-full flex items-center p-2 rounded hover:bg-light-ui-2 dark:hover:bg-dark-ui-2
                   text-left border border-light-ui-3 dark:border-dark-ui-3 mb-3"
        >
            <div
                class="w-8 h-8 rounded-full bg-primary flex items-center justify-center text-white text-xs font-bold mr-3"
            >
                {getInitials($user?.display_name)}
            </div>
            <div class="flex flex-col">
                <span
                    class="text-sm font-medium text-light-tx dark:text-dark-tx"
                    >{$user?.display_name ?? "–"}</span
                >
            </div>
        </button>

        {#if menuOpen}
            <UserMenu onClose={closeMenu} />
        {/if}
    </div>
    <!-- Quick-Links -->
    <div class="space-y-1 mb-0 flex gap-3 text-xs ml-0">
        <a
            href="#"
            class="flex items-center text-xs text-light-tx-2 dark:text-dark-tx-2
                   hover:text-primary dark:hover:text-primary-dark
                   hover:bg-light-ui dark:hover:bg-dark-ui rounded px-0 py-1"
        >
            <HelpCircle class="w-4 h-4 mr-1" />
            Hilfe
        </a>
        <a
            href="#"
            class="flex items-center text-xs text-light-tx-2 dark:text-dark-tx-2
                   hover:text-primary dark:hover:text-primary-dark
                   hover:bg-light-ui dark:hover:bg-dark-ui rounded px-0 py-1"
        >
            <Info class="w-4 h-4 mr-1" />
            Datenschutz
        </a>
        <a
            href="#"
            class="flex items-center text-xs text-light-tx-2 dark:text-dark-tx-2
                   hover:text-primary dark:hover:text-primary-dark
                   hover:bg-light-ui dark:hover:bg-dark-ui rounded px-0 py-1 mb-1"
        >
            <AlertTriangle class="w-4 h-4 mr-1" />
            Regeln
        </a>
    </div>
</div>
