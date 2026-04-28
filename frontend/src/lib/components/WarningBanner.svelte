<script>
    import { TriangleAlert } from "lucide-svelte";
    let { message } = $props();
</script>

<div
    class="flex items-center gap-3 p-4 rounded border
        bg-light-ye-2 dark:bg-dark-ye-2
        border-light-ye dark:border-dark-ye
        text-dark-tx dark:text-light-tx mb-4"
>
    <TriangleAlert class="w-5 h-5 shrink-0" />
    <span class="text-sm">{message}</span>
</div>
