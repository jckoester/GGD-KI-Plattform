<script>
    import { AlertCircle } from 'lucide-svelte';
    import { renderMarkdown } from '$lib/markdown.js';

    let { message, isStreaming = false, costEur = null } = $props();

    let renderedContent = $derived(
        message.role === 'assistant' ? renderMarkdown(message.content) : ''
    );

    // Svelte-Action: Copy-Buttons in code-block-Containern einbinden
    function copyButtons(node) {
        function attachButtons() {
            node.querySelectorAll('.code-block:not([data-copy-attached])').forEach(block => {
                block.setAttribute('data-copy-attached', '');

                const btn = document.createElement('button');
                btn.setAttribute('aria-label', 'Code kopieren');
                btn.className = [
                    'copy-btn',
                    'absolute top-1.5 right-1.5',
                    'px-1.5 py-0.5 rounded text-xs',
                    'bg-light-ui-2 dark:bg-dark-ui-2',
                    'text-light-tx-2 dark:text-dark-tx-2',
                    'hover:bg-light-ui-3 dark:hover:bg-dark-ui-3',
                    'transition-colors',
                ].join(' ');
                btn.textContent = 'Kopieren';

                btn.addEventListener('click', async () => {
                    const code = block.querySelector('code')?.textContent ?? '';
                    try {
                        await navigator.clipboard.writeText(code);
                        btn.textContent = '\u2713';
                        setTimeout(() => { btn.textContent = 'Kopieren'; }, 1500);
                    } catch {
                        btn.textContent = 'Fehler';
                        setTimeout(() => { btn.textContent = 'Kopieren'; }, 1500);
                    }
                });

                block.appendChild(btn);
            });
        }

        attachButtons();

        // Re-trigger wenn Inhalt sich ändert (Streaming: neue Code-Blöcke erscheinen)
        const observer = new MutationObserver(attachButtons);
        observer.observe(node, { childList: true, subtree: true });

        return {
            destroy() { observer.disconnect(); }
        };
    }
</script>

{#if message.role === 'user'}
    <div class="flex justify-end">
        <div class="bg-primary dark:bg-primary-dark text-white rounded-xl rounded-br-none px-4 py-2 max-w-[80%]">
            <p class="whitespace-pre-wrap">{message.content}</p>
        </div>
    </div>

{:else if message.role === 'assistant'}
    <div class="flex justify-start">
        <div class="bg-light-secondary dark:bg-dark-secondary rounded-xl rounded-bl-none px-4 py-3 max-w-[80%]">
            <div class="prose dark:prose-invert max-w-none
                        prose-p:my-1 prose-headings:mt-3 prose-headings:mb-1
                        prose-pre:p-0 prose-pre:bg-transparent prose-pre:rounded-none prose-pre:my-0
                        prose-code:bg-transparent prose-code:before:content-none prose-code:after:content-none
                        prose-p:text-light-tx dark:prose-p:text-dark-tx
                        prose-headings:text-light-tx dark:prose-headings:text-dark-tx
                        prose-strong:text-light-tx dark:prose-strong:text-dark-tx
                        prose-a:text-light-bl dark:prose-a:text-dark-bl
                        prose-code:text-light-tx dark:prose-code:text-dark-tx
                        prose-blockquote:text-light-tx-2 dark:prose-blockquote:text-dark-tx-2"
                 use:copyButtons>
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
