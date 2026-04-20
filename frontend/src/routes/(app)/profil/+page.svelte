<script>
    import { Sun, Moon, Monitor } from "lucide-svelte";
    import { themePref } from "$lib/stores/theme.js";
    import { goto } from "$app/navigation";

    const options = [
        { value: "light", label: "Hell", Icon: Sun },
        { value: "dark", label: "Dunkel", Icon: Moon },
        { value: "system", label: "System", Icon: Monitor },
    ];

    // Mock-Funktion, alle Einstellungen speichern automatisch bei Änderungen. Der Button führt nur zurück auf die Startseite
    function doSave() {
        goto("/");
    }
</script>

<div class="max-w-2xl mx-auto p-6">
    <h1 class="text-2xl font-bold mb-6 text-light-tx dark:text-dark-tx">
        Profil
    </h1>

    <section class="mb-8">
        <h2
            class="text-base font-semibold mb-3 text-light-tx-2 dark:text-dark-tx-2"
        >
            Darstellungsmodus
        </h2>
        <div class="flex gap-2">
            {#each options as { value, label, Icon }}
                <button
                    class="flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors
                        {$themePref === value
                        ? 'bg-primary text-white'
                        : 'bg-light-ui dark:bg-dark-ui text-light-tx dark:text-dark-tx hover:bg-light-ui-2 dark:hover:bg-dark-ui-2'}"
                    onclick={() => themePref.set(value)}
                >
                    <Icon class="w-4 h-4" />
                    {label}
                </button>
            {/each}
        </div>
    </section>
    <section class="mb-8">
        <button
            class="px-4 py-2 rounded-md text-sm font-medium bg-light-gr-2 dark:bg-dark-gr-2 text-white hover:bg-light-gr dark:hover:bg-dark-gr transition-colors"
            onclick={doSave}
        >
            Speichern
        </button>
    </section>
</div>
