<script>
    import { TriangleAlert } from "lucide-svelte";
    let { message } = $props();
</script>

<div
    class="flex items-center gap-3 p-4 rounded border
        bg-light-ye-bg dark:bg-dark-ye-bg
        border-light-ye dark:border-dark-ye
        text-light-tx dark:text-dark-tx mb-4"
>
    <TriangleAlert class="w-5 h-5 shrink-0 text-light-ye dark:text-dark-ye" />
    <span class="text-sm">{message}</span>
</div>
