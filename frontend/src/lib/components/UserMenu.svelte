<script>
    import { user } from "$lib/stores/user.js";
    import { goto } from "$app/navigation";
    import { Shield, User, LogOut, Eye, Wallet, BarChart2 } from "lucide-svelte";
    import { logout } from "$lib/api.js";
    import { onMount } from "svelte";

    export let onClose = () => {};

    let menuRef;

    async function doLogout() {
        await logout();
        sessionStorage.removeItem('display_name');
        goto('/');
        onClose();
    }

    function handleClickOutside(event) {
        if (menuRef && !menuRef.contains(event.target)) {
            onClose();
        }
    }

    onMount(() => {
        window.addEventListener('click', handleClickOutside);
        return () => window.removeEventListener('click', handleClickOutside);
    });
</script>

<div
    bind:this={menuRef}
    class="absolute bottom-16 left-0 right-0 mx-3 bg-white rounded-md shadow-lg border border-gray-200 py-1 z-50"
>
    <!-- Admin (nur bei admin-Rolle) -->
    {#if $user?.roles.includes('admin')}
        <a href="/admin" class="flex items-center px-4 py-2 text-sm text-gray-700 hover:bg-gray-100">
            <Shield class="w-4 h-4 mr-3" />
            Admin
        </a>
    {/if}

    <!-- Review (nur bei review-Rolle) - vorbereitet für später -->
    {#if $user?.roles.includes('review')}
        <a href="#" class="flex items-center px-4 py-2 text-sm text-gray-700 hover:bg-gray-100">
            <Eye class="w-4 h-4 mr-3" />
            Review
        </a>
    {/if}

    <!-- Budget (nur bei budget-Rolle) - vorbereitet für später -->
    {#if $user?.roles.includes('budget')}
        <a href="#" class="flex items-center px-4 py-2 text-sm text-gray-700 hover:bg-gray-100">
            <Wallet class="w-4 h-4 mr-3" />
            Budget
        </a>
    {/if}

    <!-- Statistik (nur bei statistics-Rolle) - vorbereitet für später -->
    {#if $user?.roles.includes('statistics')}
        <a href="#" class="flex items-center px-4 py-2 text-sm text-gray-700 hover:bg-gray-100">
            <BarChart2 class="w-4 h-4 mr-3" />
            Statistik
        </a>
    {/if}

    <!-- Trenner wenn Rollen-Menüs vorhanden -->
    {#if $user?.roles.some(r => ['admin', 'review', 'budget', 'statistics'].includes(r))}
        <div class="border-t border-gray-200 my-1"></div>
    {/if}

    <!-- Profil (immer sichtbar) -->
    <a href="#" class="flex items-center px-4 py-2 text-sm text-gray-700 hover:bg-gray-100">
        <User class="w-4 h-4 mr-3" />
        Profil
    </a>

    <!-- Trenner -->
    <div class="border-t border-gray-200 my-1"></div>

    <!-- Abmelden (immer sichtbar) -->
    <button
        onclick={doLogout}
        class="w-full flex items-center px-4 py-2 text-sm text-red-600 hover:bg-red-50"
    >
        <LogOut class="w-4 h-4 mr-3" />
        Abmelden
    </button>
</div>
