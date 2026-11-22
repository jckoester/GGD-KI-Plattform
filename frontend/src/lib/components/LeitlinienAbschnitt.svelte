<script>
    /**
     * Leitlinien der Schule (0.50, Päckchen AT) — Abschnitt auf der Seite *Leitperspektiven*.
     *
     * Je Leitlinie ein aufklappbarer Kopf, darin ihre Aspekte. Zugeordnet wird über Kürzel
     * (`metadata.leitlinie` am Aspekt), nicht über Kanten — siehe `app/context/leitlinien.py`.
     * Anlegen und Bearbeiten laufen über die Sammlungsformulare; die Knöpfe sehen nur Admins
     * (der Server prüft es ohnehin).
     *
     * Props:
     *   nodes    — Knoten der Typen `leitbild` und `leitbild_aspekt`
     *   istAdmin — Knöpfe zum Anlegen zeigen
     *   nodeHref — (id) => Adresse der Detailansicht
     *   zurueck  — Rückweg für die Formulare
     */
    import { ChevronDown, ChevronRight, ExternalLink, LayoutGrid, Plus } from 'lucide-svelte'
    import NodeTypeIcon from '$lib/components/NodeTypeIcon.svelte'
    import { kuerzelVergleich } from '$lib/hinweise.js'

    let { nodes = [], istAdmin = false, nodeHref, zurueck = '/knowledge/cross-cutting-themes' } = $props()

    const k = (n, feld) => String(n.metadata?.[feld] ?? '').replace(/\s+/g, '').toUpperCase()

    const leitlinien = $derived(
        nodes
            .filter((n) => n.content_type === 'leitbild')
            .sort((a, b) => kuerzelVergleich(k(a, 'kuerzel'), k(b, 'kuerzel')))
            .map((lb) => ({
                ...lb,
                kuerzel: k(lb, 'kuerzel'),
                aspekte: nodes
                    .filter((a) => a.content_type === 'leitbild_aspekt' && k(a, 'leitlinie') === k(lb, 'kuerzel'))
                    .sort((a, b) => kuerzelVergleich(k(a, 'kuerzel'), k(b, 'kuerzel'))),
            })),
    )

    let offen = $state({})
    const umschalten = (id) => (offen = { ...offen, [id]: !offen[id] })

    const back = $derived(`back=${encodeURIComponent(zurueck)}`)
</script>

<section class="mt-10" aria-labelledby="leitlinien-titel">
    <div class="flex items-center justify-between gap-3 mb-3">
        <div>
            <h2 id="leitlinien-titel" class="text-xl font-semibold text-light-tx dark:text-dark-tx">
                Leitlinien der Schule
            </h2>
            <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mt-1">
                Eigene Rahmenwerke der Schule, etwa die Nachhaltigkeitsziele. Im Curriculum verweist
                du mit <code>@</code> auf sie, wie auf eine Leitperspektive.
            </p>
        </div>
        {#if istAdmin}
            <a
                href="/knowledge/collections/leitbild/new?{back}"
                class="shrink-0 inline-flex items-center gap-1 px-3 py-1.5 rounded text-sm
                       bg-primary dark:bg-primary-dark text-on-fill hover:opacity-90"
            >
                <Plus class="w-4 h-4" /> Leitlinie anlegen
            </a>
        {/if}
    </div>

    {#if leitlinien.length === 0}
        <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
            Die Schule hat noch keine Leitlinien hinterlegt.
        </p>
    {:else}
        <div class="space-y-4">
            {#each leitlinien as lb (lb.id)}
                <div class="bg-light-bg-2 dark:bg-dark-bg-2 rounded-lg border border-light-ui-3 dark:border-dark-ui-3 overflow-hidden">
                    <div class="w-full flex items-center justify-between gap-3 bg-light-bg-3 dark:bg-dark-bg-3">
                        <div class="flex items-center gap-2 min-w-0 pl-4">
                            <button
                                onclick={() => umschalten(lb.id)}
                                aria-expanded={!!offen[lb.id]}
                                class="flex items-center gap-3 min-w-0 py-4 text-left text-light-tx dark:text-dark-tx"
                            >
                                <NodeTypeIcon contentType="leitbild" size={20} />
                                <span class="font-medium truncate">{lb.title}</span>
                                <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">{lb.kuerzel}</span>
                            </button>
                            <a
                                href={nodeHref(lb.id)}
                                title="Baustein öffnen"
                                aria-label="Leitlinie {lb.title} öffnen"
                                class="shrink-0 p-1 rounded text-light-tx-2 dark:text-dark-tx-2 hover:text-primary dark:hover:text-dark-bl"
                            >
                                <ExternalLink class="w-4 h-4" />
                            </a>
                            <a
                                href="/knowledge/cross-cutting-themes/{lb.id}/overview"
                                title="Übersicht: wo die Aspekte im Unterricht vorkommen"
                                aria-label="Übersicht zu {lb.title}"
                                class="shrink-0 p-1 rounded text-light-tx-2 dark:text-dark-tx-2 hover:text-primary dark:hover:text-dark-bl"
                            >
                                <LayoutGrid class="w-4 h-4" />
                            </a>
                        </div>
                        <button
                            onclick={() => umschalten(lb.id)}
                            aria-label="Aspekte von {lb.title} {offen[lb.id] ? 'einklappen' : 'aufklappen'}"
                            class="flex items-center gap-2 py-4 pr-4 pl-2 shrink-0 text-light-tx dark:text-dark-tx"
                        >
                            <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">{lb.aspekte.length} Aspekte</span>
                            {#if offen[lb.id]}
                                <ChevronDown class="w-4 h-4 shrink-0" />
                            {:else}
                                <ChevronRight class="w-4 h-4 shrink-0" />
                            {/if}
                        </button>
                    </div>

                    {#if offen[lb.id]}
                        <div class="p-3 space-y-1 border-t border-light-ui-3 dark:border-dark-ui-3">
                            {#each lb.aspekte as aspekt (aspekt.id)}
                                <a
                                    href={nodeHref(aspekt.id)}
                                    class="flex items-center gap-3 p-2 rounded hover:bg-light-bg-3 dark:hover:bg-dark-bg-3
                                           text-light-tx dark:text-dark-tx text-sm"
                                >
                                    <NodeTypeIcon contentType="leitbild_aspekt" size={16} />
                                    <span class="text-xs text-light-tx-2 dark:text-dark-tx-2 w-16 shrink-0">{k(aspekt, 'kuerzel')}</span>
                                    <span class="flex-1">{aspekt.title}</span>
                                </a>
                            {:else}
                                <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 p-2">Noch keine Aspekte.</p>
                            {/each}
                            {#if istAdmin}
                                <a
                                    href="/knowledge/collections/leitbild_aspekt/new?leitlinie={encodeURIComponent(lb.kuerzel)}&{back}"
                                    class="inline-flex items-center gap-1 mt-2 px-2 py-1 rounded text-sm
                                           text-light-bl dark:text-dark-bl hover:bg-light-bg-3 dark:hover:bg-dark-bg-3"
                                >
                                    <Plus class="w-4 h-4" /> Aspekt hinzufügen
                                </a>
                            {/if}
                        </div>
                    {/if}
                </div>
            {/each}
        </div>
    {/if}
</section>
