<script>
    import { ReceiptEuro, ArrowLeft } from "lucide-svelte";
</script>

<button
    onclick={() => history.back()}
    class="flex items-center gap-1 mb-4 text-sm text-light-tx-2 dark:text-dark-tx-2 hover:text-light-tx dark:hover:text-dark-tx transition-colors"
>
    <ArrowLeft class="w-4 h-4" /> Zurück
</button>

<div class="max-w-4xl mx-auto py-8">
    <div class="flex items-center gap-2 mb-6 text-light-tx dark:text-dark-tx">
        <ReceiptEuro class="w-6 h-6" />
        <h1 class="text-2xl font-semibold">Kosten</h1>
    </div>
    <p class="text-light-tx-2 dark:text-dark-tx-2">
        Wird in Schritt 7d-3 implementiert.
    </p>
</div>
