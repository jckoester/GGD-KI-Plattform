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

<div class="h-full overflow-y-auto px-4 py-4">
    <h1 class="text-light-tx dark:text-dark-tx">Hauptinhalt - Hello-Seite</h1>

    {#if user}
        <div
            class="bg-light-bg dark:bg-dark-ui shadow-sm border border-light-ui-3 dark:border-dark-ui-3 p-8 max-w-sm w-full"
        >
            <h1 class="text-xl font-semibold text-light-tx dark:text-dark-tx mb-4">
                Willkommen!
            </h1>
            <dl class="space-y-2 text-sm text-light-tx-2 dark:text-dark-tx-2">
                <div class="flex justify-between">
                    <dt>Rolle</dt>
                    <dd class="font-medium text-light-tx dark:text-dark-tx">
                        {roleLabel(user.role)}
                    </dd>
                </div>
                {#if user.grade}
                    <div class="flex justify-between">
                        <dt>Klasse</dt>
                        <dd class="font-medium text-light-tx dark:text-dark-tx">
                            {user.grade}
                        </dd>
                    </div>
                {/if}
            </dl>
        </div>
    {/if}
</div>
