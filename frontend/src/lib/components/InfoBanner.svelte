<script>
    import { Info } from "lucide-svelte";
    let { message } = $props();
</script>

<div
    class="flex items-center gap-3 p-4 rounded border
        bg-light-bl-2 dark:bg-dark-bl-2
        border-light-bl dark:border-dark-bl
        text-dark-tx dark:text-light-tx mb-4"
>
    <Info class="w-5 h-5 shrink-0" />
    <span class="text-sm">{message}</span>
</div>
