<script>
    import { ChartNoAxesCombined, ChartColumn, ReceiptEuro, ArrowLeft } from "lucide-svelte";
</script>

<button
    onclick={() => history.back()}
    class="flex items-center gap-1 mb-4 text-sm text-light-tx-2 dark:text-dark-tx-2 hover:text-light-tx dark:hover:text-dark-tx transition-colors"
>
    <ArrowLeft class="w-4 h-4" /> Zurück
</button>

<div class="max-w-2xl mx-auto py-8">
    <div class="flex items-center gap-2 mb-6 text-light-tx dark:text-dark-tx">
        <ChartNoAxesCombined class="w-6 h-6" />
        <h1 class="text-2xl font-semibold">Statistics</h1>
    </div>
    <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <a
            href="/statistics/prompts"
            class="bg-light-ui dark:bg-dark-ui border border-light-ui-3 dark:border-dark-ui-3
                    rounded-lg p-5 hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors
                    block no-underline"
        >
            <ChartColumn class="w-6 h-6 mb-2 text-light-tx-2 dark:text-dark-tx-2" />
            <div class="font-medium text-light-tx dark:text-dark-tx">Prompts</div>
            <div class="text-sm text-light-tx-2 dark:text-dark-tx-2 mt-1">
                Nutzungs-Heatmap nach Wochentag und Uhrzeit
            </div>
        </a>
        <a
            href="/statistics/costs"
            class="bg-light-ui dark:bg-dark-ui border border-light-ui-3 dark:border-dark-ui-3
                    rounded-lg p-5 hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors
                    block no-underline"
        >
            <ReceiptEuro class="w-6 h-6 mb-2 text-light-tx-2 dark:text-dark-tx-2" />
            <div class="font-medium text-light-tx dark:text-dark-tx">Costs</div>
            <div class="text-sm text-light-tx-2 dark:text-dark-tx-2 mt-1">
                Budgetverbrauch nach Zeitraum und Jahrgang
            </div>
        </a>
    </div>
</div>
