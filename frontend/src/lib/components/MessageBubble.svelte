<script>
    import { AlertCircle } from 'lucide-svelte';
    import { renderMarkdown } from '$lib/markdown.js';

    let { message, isStreaming = false, costEur = null } = $props();

    let renderedContent = $derived(
        message.role === 'assistant' ? renderMarkdown(message.content) : ''
    );
</script>

{#if message.role === 'user'}
    <div class="flex justify-end">
        <div class="bg-primary dark:bg-primary-dark text-white rounded-xl rounded-br-none px-4 py-2 max-w-[80%]">
            <p class="whitespace-pre-wrap">{message.content}</p>
        </div>
    </div>

{:else if message.role === 'assistant'}
    <div class="flex justify-start">
        <div class="bg-light-bg dark:bg-dark-bg rounded-xl rounded-bl-none px-4 py-3 max-w-[80%]">
            <div class="prose prose-sm dark:prose-invert max-w-none
                        prose-p:my-1 prose-headings:mt-3 prose-headings:mb-1
                        prose-pre:p-0 prose-pre:bg-transparent prose-pre:m-0
                        prose-p:text-light-tx dark:prose-p:text-dark-tx
                        prose-headings:text-light-tx dark:prose-headings:text-dark-tx
                        prose-strong:text-light-tx dark:prose-strong:text-dark-tx
                        prose-a:text-light-bl dark:prose-a:text-dark-bl
                        prose-code:text-light-tx dark:prose-code:text-dark-tx
                        prose-blockquote:text-light-tx-2 dark:prose-blockquote:text-dark-tx-2">
                {@html renderedContent}
            </div>
            {#if isStreaming}
                <span class="animate-pulse cursor-default text-light-tx-2 dark:text-dark-tx-2 text-sm ml-0.5">|</span>
            {/if}
            {#if costEur !== null}
                <p class="text-xs text-light-tx-2 dark:text-dark-tx-2 mt-2 pt-1
                           border-t border-light-ui-3 dark:border-dark-ui-3">
                    {costEur} €
                </p>
            {/if}
        </div>
    </div>

{:else if message.role === 'error'}
    <div class="w-full">
        <div class="flex items-start gap-2 bg-red-50 dark:bg-red-950/20
                    border border-red-200 dark:border-red-900
                    rounded-lg px-4 py-3 text-red-600 dark:text-red-400">
            <AlertCircle class="w-4 h-4 mt-0.5 shrink-0" />
            <p class="text-sm whitespace-pre-wrap">{message.content}</p>
        </div>
    </div>
{/if}
