<script>
    import { CircleCheck } from "lucide-svelte";
    let { message } = $props();
</script>

<div
    class="flex items-center gap-3 p-4 rounded border
        bg-light-gr-bg dark:bg-dark-gr-bg
        border-light-gr dark:border-dark-gr
        text-light-tx dark:text-dark-tx mb-4"
>
    <CircleCheck class="w-5 h-5 shrink-0 text-light-gr dark:text-dark-gr" />
    <span class="text-sm">{message}</span>
</div>
