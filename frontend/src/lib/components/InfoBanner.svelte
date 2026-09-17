<script>
    import { Info } from "lucide-svelte";
    let { message } = $props();
</script>

<div
    class="flex items-center gap-3 p-4 rounded border
        bg-light-bl-bg dark:bg-dark-bl-bg
        border-light-bl dark:border-dark-bl
        text-light-tx dark:text-dark-tx mb-4"
>
    <Info class="w-5 h-5 shrink-0 text-light-bl dark:text-dark-bl" />
    <span class="text-sm">{message}</span>
</div>
