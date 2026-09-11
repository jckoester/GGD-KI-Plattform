<script>
    /**
     * Hilfe-Ressourcen zu einem Krisenhinweis (ADR-008 Teil 3/4).
     *
     * **Dezent, nicht alarmierend** — und deshalb keine Warnfarbe. Der Kasten liegt
     * auf der gewöhnlichen erhöhten Fläche (`bg-*-bg-2`) und trägt links eine grüne
     * Kante: ruhig, aber unverwechselbar kein Chatbeitrag.
     *
     * ⚠️ **Was hier vorher stand und warum es weg ist** (nachgemessen 10.09.2026):
     * Der Kasten hatte `bg-light-bl-2` (#4385be) — dieselbe Blaufamilie wie die
     * Nutzer-Blase (`bg-primary`, #205ea6); zwischen beiden liegen 1,66:1, sie waren
     * nebeneinander kaum zu trennen. Schlimmer: Die Kontaktzeilen standen in
     * `text-light-tx-2` (#6f6e69) **auf** diesem Blau — 1,30:1, bei einer
     * Untergrenze von 4,5:1. Sie waren im Hellmodus schlicht nicht lesbar.
     *
     * Die Textfarben sind jetzt die gewohnten auf der gewohnten Fläche. Damit ist
     * das Problem strukturell weg statt übertüncht: Wer den Kasten später anfasst,
     * muss nicht wissen, dass hier andere Regeln galten.
     *
     * topic: { help_topic, label, internal: Contact[], external: Contact[] }
     * Contact: { name, contact?, hours?, email?, phone?, website?, free_of_charge?, anonymous? }
     */
    import { LifeBuoy, Phone, Mail, Clock, ExternalLink } from "lucide-svelte";

    let { topic } = $props();
</script>

{#snippet contactRow(c)}
    <div class="leading-snug">
        <span class="font-medium text-light-tx dark:text-dark-tx">{c.name}</span>
        {#if c.contact}<span class="text-light-tx dark:text-dark-tx"> — {c.contact}</span>{/if}
        <!-- Die Zeile mit Telefon, Zeiten und Adresse ist die eigentliche Auskunft;
             sie steht deshalb in der vollen Textfarbe, nicht in der abgeschwächten.
             `tx-2` läge auf dieser Fläche bei 4,47:1 — knapp unter der Grenze. -->
        <div
            class="flex flex-wrap items-center gap-x-3 gap-y-0.5 mt-0.5
                   text-light-tx dark:text-dark-tx"
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
    class="my-2 rounded-lg border border-l-4 p-4 text-sm
           bg-light-bg-2 dark:bg-dark-bg-2
           border-light-gr dark:border-dark-gr
           border-l-light-gr dark:border-l-dark-gr
           text-light-tx dark:text-dark-tx"
>
    <div class="flex items-center gap-2 font-medium mb-2">
        <LifeBuoy class="w-5 h-5 shrink-0 text-light-gr dark:text-dark-gr" />
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
