<script>
    import content from '$docs/datenschutz.md?raw';
    import { renderMarkdown } from '$lib/markdown.js';
</script>

<div class="max-w-2xl mx-auto p-6 md:p-8">
    <div class="prose dark:prose-invert max-w-none">
        {@html renderMarkdown(content)}
    </div>
</div>
