<script>
    // Dezentes, NICHT alarmierendes Hilfe-Banner (ADR-008 Teil 3/4).
    // topic: { help_topic, label, internal: Contact[], external: Contact[] }
    // Contact: { name, contact?, hours?, email?, phone?, website?, free_of_charge?, anonymous? }
    import { LifeBuoy, Phone, Mail, Clock, ExternalLink } from "lucide-svelte";

    let { topic } = $props();
</script>

{#snippet contactRow(c)}
    <div class="leading-snug">
        <span class="font-medium text-light-tx dark:text-dark-tx">{c.name}</span>
        {#if c.contact}<span class="text-light-tx-2 dark:text-dark-tx-2"> — {c.contact}</span>{/if}
        <div
            class="flex flex-wrap items-center gap-x-3 gap-y-0.5 mt-0.5
                   text-light-tx-2 dark:text-dark-tx-2"
        >
            {#if c.phone}
                <span class="inline-flex items-center gap-1"
                    ><Phone class="w-3.5 h-3.5 shrink-0" />{c.phone}</span
                >
            {/if}
            {#if c.hours}
                <span class="inline-flex items-center gap-1"
                    ><Clock class="w-3.5 h-3.5 shrink-0" />{c.hours}</span
                >
            {/if}
            {#if c.email}
                <a
                    class="inline-flex items-center gap-1 underline hover:no-underline"
                    href="mailto:{c.email}"
                    ><Mail class="w-3.5 h-3.5 shrink-0" />{c.email}</a
                >
            {/if}
            {#if c.website}
                <a
                    class="inline-flex items-center gap-1 underline hover:no-underline"
                    href={c.website}
                    target="_blank"
                    rel="noopener noreferrer"
                    ><ExternalLink class="w-3.5 h-3.5 shrink-0" />Website</a
                >
            {/if}
            {#if c.free_of_charge}<span>kostenlos</span>{/if}
            {#if c.anonymous}<span>anonym</span>{/if}
        </div>
    </div>
{/snippet}

<div
    class="mt-2 rounded border p-4 text-sm
           bg-light-bl-2 dark:bg-dark-bl-2
           border-light-bl dark:border-dark-bl
           text-light-tx dark:text-dark-tx"
>
    <div class="flex items-center gap-2 font-medium mb-2">
        <LifeBuoy class="w-5 h-5 shrink-0" />
        <span>{topic.label}</span>
    </div>

    {#if topic.internal?.length}
        <p class="text-light-tx-2 dark:text-dark-tx-2 mb-1">In der Schule</p>
        <ul class="space-y-1.5 mb-3">
            {#each topic.internal as c}
                <li>{@render contactRow(c)}</li>
            {/each}
        </ul>
    {/if}

    {#if topic.external?.length}
        <p class="text-light-tx-2 dark:text-dark-tx-2 mb-1">Auch außerhalb der Schule</p>
        <ul class="space-y-1.5">
            {#each topic.external as c}
                <li>{@render contactRow(c)}</li>
            {/each}
        </ul>
    {/if}
</div>
