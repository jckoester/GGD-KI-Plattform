<script>
    import { LoaderCircle } from "lucide-svelte";
    let { message = "Lädt…" } = $props();
</script>

<div
    class="flex items-center gap-3 p-4 rounded border
        bg-light-bg dark:bg-dark-bg
        border-light-tx-2 dark:border-dark-tx-2
        text-light-tx-2 dark:text-dark-tx-2"
>
    <LoaderCircle class="w-5 h-5 animate-spin shrink-0" />
    <span>{message}</span>
</div>
