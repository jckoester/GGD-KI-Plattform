<script>
    import content from '$docs/README.md?raw';
    import { renderMarkdown } from '$lib/markdown.js';
</script>

<!-- Rahmen schmal wie alle Leseseiten (0.48), die Textspalte bleibt auf Lesebreite (G8 a). -->
<div class="max-w-4xl mx-auto px-6 py-6">
    <div class="prose dark:prose-invert max-w-prose">
        {@html renderMarkdown(content, { dokuLinks: true })}
    </div>
</div>
