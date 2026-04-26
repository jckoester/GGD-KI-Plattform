<script>
    import {
        Settings,
        CloudCog,
        ShieldCheck,
        BarChart2,
        PiggyBank,
        ArrowLeft,
    } from "lucide-svelte";
</script>

<button
    onclick={() => history.back()}
    class="flex items-center gap-1 mb-4 text-sm text-light-tx-2 dark:text-dark-tx-2 hover:text-light-tx dark:hover:text-dark-tx transition-colors"
>
    <ArrowLeft class="w-4 h-4" /> Zurück
</button>

<div class="max-w-2xl mx-auto py-8">
    <div class="flex items-center gap-2 mb-6 text-light-tx dark:text-dark-tx">
        <Settings class="w-6 h-6" />
        <h1 class="text-2xl font-semibold">Einstellungen</h1>
    </div>
    <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <!-- Modell-Freischaltung (7b) -->
        <div
            class="bg-light-ui dark:bg-dark-ui border border-light-ui-3 dark:border-dark-ui-3
                    rounded-lg p-5 opacity-40 cursor-not-allowed select-none"
        >
            <CloudCog
                class="w-6 h-6 mb-2 text-light-tx-2 dark:text-dark-tx-2"
            />
            <div class="font-medium text-light-tx dark:text-dark-tx">
                Modell-Freischaltung
            </div>
            <div class="text-sm text-light-tx-2 dark:text-dark-tx-2 mt-1">
                Folgt in Schritt 7b
            </div>
        </div>
        <!-- Einstellungen (7f) -->
        <div
            class="bg-light-ui dark:bg-dark-ui border border-light-ui-3 dark:border-dark-ui-3
                    rounded-lg p-5 opacity-40 cursor-not-allowed select-none"
        >
            <Settings
                class="w-6 h-6 mb-2 text-light-tx-2 dark:text-dark-tx-2"
            />
            <div class="font-medium text-light-tx dark:text-dark-tx">
                Einstellungen
            </div>
            <div class="text-sm text-light-tx-2 dark:text-dark-tx-2 mt-1">
                Folgt in Schritt 7f
            </div>
        </div>
    </div>
</div>
