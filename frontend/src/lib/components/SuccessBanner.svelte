<script>
    import { CircleCheck } from "lucide-svelte";
    let { message } = $props();
</script>

<div
    class="flex items-center gap-3 p-4 rounded border
        bg-light-gr-2 dark:bg-dark-gr-2
        border-light-gr dark:border-dark-gr
        text-dark-tx dark:text-light-tx mb-4"
>
    <CircleCheck class="w-5 h-5 shrink-0" />
    <span class="text-sm">{message}</span>
</div>
