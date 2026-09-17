<script>
    import { CircleX } from "lucide-svelte";
    let { message } = $props();
</script>

<div
    class="flex items-center gap-3 p-4 rounded border
        bg-light-re-bg dark:bg-dark-re-bg
        border-light-re dark:border-dark-re
        text-light-tx dark:text-dark-tx mb-4"
>
    <CircleX class="w-5 h-5 shrink-0 text-light-re dark:text-dark-re" />
    <span class="text-sm">{message}</span>
</div>
