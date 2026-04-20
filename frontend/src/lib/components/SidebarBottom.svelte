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

<div class="pb-0 p-3 border-t border-gray-200 flex-shrink-0">
    <!-- Budget-Zeile -->
    <div class="flex items-center text-xs text-gray-500 mb-3">
        <Coins class="w-3 h-3 mr-2" />
        <span>–/– €</span>
        <span class="ml-auto text-xs">r: –</span>
    </div>

    <!-- Benutzerbereich -->
    <div class="relative">
        <button
            onclick={toggleMenu}
            class="w-full flex items-center p-2 rounded hover:bg-gray-100 text-left border border-gray-300 mb-3"
        >
            <div
                class="w-8 h-8 rounded-full bg-primary flex items-center justify-center text-white text-xs font-bold mr-3"
            >
                {getInitials($user?.display_name)}
            </div>
            <div class="flex flex-col">
                <span class="text-sm font-medium text-gray-800"
                    >{$user?.display_name ?? "–"}</span
                >
                <span class="text-xs text-gray-400">ki@ggd</span>
            </div>
        </button>

        {#if menuOpen}
            <UserMenu onClose={closeMenu} />
        {/if}
    </div>
    <!-- Quick-Links -->
    <div class="space-y-1 mb-0 flex gap-2 text-xs ml-0">
        <a
            href="#"
            class="flex items-center text-xs text-gray-600 hover:text-primary hover:bg-gray-100 rounded px-0 py-1"
        >
            <HelpCircle class="w-4 h-4 mr-2" />
            Hilfe
        </a>
        <a
            href="#"
            class="flex items-center text-xs text-gray-600 hover:text-primary hover:bg-gray-100 rounded px-0 py-1"
        >
            <Info class="w-4 h-4 mr-2" />
            Datenschutz
        </a>
        <a
            href="#"
            class="flex items-center text-xs text-gray-600 hover:text-primary hover:bg-gray-100 rounded px-0 py-1"
        >
            <AlertTriangle class="w-4 h-4 mr-2" />
            Regeln
        </a>
    </div>
</div>
