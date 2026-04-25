<script>
    import { ShieldCheck, BarChart2, PiggyBank, Settings } from 'lucide-svelte'
</script>

<div class="max-w-2xl mx-auto py-8">
    <h1 class="text-2xl font-semibold text-light-tx dark:text-dark-tx mb-6">
        Administration
    </h1>
    <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <!-- Modell-Freischaltung (7b) -->
        <div class="bg-light-ui dark:bg-dark-ui border border-light-ui-3 dark:border-dark-ui-3
                    rounded-lg p-5 opacity-40 cursor-not-allowed select-none">
            <ShieldCheck class="w-6 h-6 mb-2 text-light-tx-2 dark:text-dark-tx-2" />
            <div class="font-medium text-light-tx dark:text-dark-tx">Modell-Freischaltung</div>
            <div class="text-sm text-light-tx-2 dark:text-dark-tx-2 mt-1">Folgt in Schritt 7b</div>
        </div>
        <!-- Einstellungen (7f) -->
        <div class="bg-light-ui dark:bg-dark-ui border border-light-ui-3 dark:border-dark-ui-3
                    rounded-lg p-5 opacity-40 cursor-not-allowed select-none">
            <Settings class="w-6 h-6 mb-2 text-light-tx-2 dark:text-dark-tx-2" />
            <div class="font-medium text-light-tx dark:text-dark-tx">Einstellungen</div>
            <div class="text-sm text-light-tx-2 dark:text-dark-tx-2 mt-1">Folgt in Schritt 7f</div>
        </div>
    </div>
</div>
