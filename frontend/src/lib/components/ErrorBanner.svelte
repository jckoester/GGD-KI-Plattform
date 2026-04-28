<script>
    import { CircleX } from "lucide-svelte";
    let { message } = $props();
</script>

<div
    class="flex items-center gap-3 p-4 rounded border
        bg-light-re-2 dark:bg-dark-re-2
        border-light-re dark:border-dark-re
        text-dark-tx dark:text-light-tx mb-4"
>
    <CircleX class="w-5 h-5 shrink-0" />
    <span class="text-sm">{message}</span>
</div>
