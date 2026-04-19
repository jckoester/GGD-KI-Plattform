<script>
    import { onMount } from "svelte";
    import { goto } from "$app/navigation";
    import { logout, getMe } from "$lib/api.js";
    import { branding } from "$lib/branding.js";

    let user = null;

    onMount(async () => {
        try {
            user = await getMe();
        } catch {
            goto("/");
        }
    });

    async function handleLogout() {
        await logout();
        goto("/");
    }

    const initials = (name) => name.slice(0, 2).toUpperCase();
    const roleLabel = (role) =>
        ({ student: "Schüler:in", teacher: "Lehrkraft", admin: "Admin" })[
            role
        ] ?? role;
</script>

<header
    class="fixed inset-x-0 top-0 h-14 bg-white border-b border-gray-200
               flex items-center justify-between px-4 z-10"
>
    <div class="flex items-center gap-2">
        {#if branding.logo_url}
            <img src={branding.logo_url} alt="Logo" class="h-8 w-auto" />
        {:else}
            <div
                class="w-8 h-8 rounded-full bg-primary flex items-center justify-center
                  text-white text-xs font-bold select-none"
            >
                {initials(branding.name)}
            </div>
        {/if}
        <span class="font-semibold text-gray-800">{branding.name}</span>
    </div>
    <button
        onclick={handleLogout}
        class="text-sm text-gray-600 hover:text-gray-900 px-3 py-1.5 rounded-lg
                 hover:bg-gray-100 transition-colors"
    >
        Abmelden
    </button>
</header>

<main
    class="pt-14 min-h-screen bg-gray-50 flex items-center justify-center p-4"
>
    {#if user}
        <div
            class="bg-white shadow-sm border border-gray-200 p-8 max-w-sm w-full"
        >
            <h1 class="text-xl font-semibold text-gray-800 mb-4">
                Willkommen!
            </h1>
            <dl class="space-y-2 text-sm text-gray-600">
                <div class="flex justify-between">
                    <dt>Rolle</dt>
                    <dd class="font-medium text-gray-800">
                        {roleLabel(user.role)}
                    </dd>
                </div>
                {#if user.grade}
                    <div class="flex justify-between">
                        <dt>Klasse</dt>
                        <dd class="font-medium text-gray-800">{user.grade}</dd>
                    </div>
                {/if}
            </dl>
            <!-- Platzhalter für Chat-Interface (Schritt 3+) -->
        </div>
    {:else}
        <p class="text-gray-400 text-sm">Lade…</p>
    {/if}
</main>
