<script>
    import { onMount } from "svelte";
    import { getMe } from "$lib/api.js";

    let user = $state(null);

    onMount(async () => {
        user = await getMe();
    });

    const roleLabel = (role) =>
        ({ student: "Schüler:in", teacher: "Lehrkraft", admin: "Admin" })[
            role
        ] ?? role;
</script>

<h1>Hauptinhalt - Hello-Seite</h1>

{#if user}
    <div class="bg-white shadow-sm border border-gray-200 p-8 max-w-sm w-full">
        <h1 class="text-xl font-semibold text-gray-800 mb-4">Willkommen!</h1>
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
{/if}
