<script>
    /**
     * Spur des Jahresverlaufsplans im Planer der Gruppe (BD Teil B, Schritt 2; FB1, Jan 26.11.2026).
     *
     * Über der Jahresübersicht die Ablaufleiste des Fachschaftsplans für Fach, Stufe und laufendes
     * Schuljahr — nur lesend, einklappbar (gemerkt in den Einstellungen, `SPUR_SCHLUESSEL`), mit
     * „heute“. Ein Block ist ein Link auf den Plan in der Bibliothek, mit `?back=` zurück in den Planer. Ohne Plan ein Satz mit
     * Verweis auf die Pläne des Fachs; ohne Fach nichts.
     *
     * „Einheiten anlegen …“ öffnet den Dialog (Schritt 5, `onEinheiten`) — nur mit Kalender.
     *
     * Props: `antwort` (von `getVerlaufsplanDerGruppe`), `fachName`, `zu` (bindable), `onUmschalten`,
     * `onEinheiten`.
     */
    import { page } from '$app/stores'
    import { mitRueckweg } from '$lib/rueckweg.js'
    import { ChevronDown, ChevronRight } from '@lucide/svelte'
    import VerlaufsplanZeitleiste from '$lib/components/VerlaufsplanZeitleiste.svelte'
    import { einheiten, spurKopf, spurOhnePlan } from '$lib/verlaufsplan.js'

    let { antwort = null, fachName = '', zu = $bindable(false), onUmschalten = () => {}, onEinheiten = null } = $props()

    const plan = $derived(antwort?.plan ?? null)
    const ohne = $derived(spurOhnePlan(antwort, fachName))
    const e = $derived(einheiten(plan?.curricula))
    const planPfad = $derived(plan ? mitRueckweg(`/knowledge/year-plans/${plan.id}`, $page.url) : '')
    const listenPfad = $derived(antwort?.subject_id != null ? `/knowledge/year-plans?fach=${antwort.subject_id}` : '/knowledge/year-plans')
    let hervor = $state(null)

    function umschalten() {
        zu = !zu
        onUmschalten(zu)
    }
</script>

{#if plan}
    <section class="mt-2 border-y border-light-ui-3 dark:border-dark-ui-3 bg-light-bg dark:bg-dark-bg px-4 py-2" aria-labelledby="verlaufsplan-spur-titel">
        <div class="flex items-center justify-between gap-3">
            <button type="button" onclick={umschalten} aria-expanded={!zu} aria-controls={zu ? undefined : 'verlaufsplan-spur-leiste'}
                class="flex items-center gap-1.5 min-w-0 text-left text-xs text-light-tx-2 dark:text-dark-tx-2 hover:text-light-tx dark:hover:text-dark-tx">
                {#if zu}<ChevronRight size={14} aria-hidden="true" />{:else}<ChevronDown size={14} aria-hidden="true" />{/if}
                <span id="verlaufsplan-spur-titel" class="font-semibold uppercase tracking-wide">Jahresverlaufsplan der Fachschaft</span>
                <span class="truncate">{spurKopf(plan)}</span>
            </button>
            <div class="flex-shrink-0 flex items-center gap-3">
                {#if onEinheiten && plan.lage}
                    <button type="button" onclick={onEinheiten}
                        class="px-2.5 py-1 text-xs rounded-md border border-light-ui-3 dark:border-dark-ui-3 text-light-tx dark:text-dark-tx hover:bg-light-bg-2 dark:hover:bg-dark-bg-2 transition-colors">
                        Einheiten anlegen …
                    </button>
                {/if}
                <a href={planPfad} class="text-xs text-light-bl dark:text-dark-bl hover:underline">Plan öffnen</a>
            </div>
        </div>
        {#if !zu}
            <div id="verlaufsplan-spur-leiste" class="mt-2">
                {#if plan.lage}
                    <VerlaufsplanZeitleiste abschnitte={plan.abschnitte} lage={plan.lage}
                        kapitelReihenfolge={e.kapitelReihenfolge} kapitelVon={e.kapitelVon}
                        planungsart={plan.planungsart} aktuell bind:hervor
                        href={planPfad} />
                {:else}
                    <p class="text-xs text-light-tx-2 dark:text-dark-tx-2">Für dieses Schuljahr liegt der Kalender der Schule noch nicht vor.</p>
                {/if}
            </div>
        {/if}
    </section>
{:else if ohne}
    <div class="mt-2 border-y border-light-ui-3 dark:border-dark-ui-3 bg-light-bg dark:bg-dark-bg px-4 py-2 text-xs text-light-tx-2 dark:text-dark-tx-2 flex items-center justify-between gap-3">
        <span>{ohne}</span>
        {#if antwort?.grund === 'kein_plan'}
            <a href={listenPfad} class="flex-shrink-0 text-light-bl dark:text-dark-bl hover:underline">Jahresverlaufspläne des Fachs</a>
        {:else if antwort?.grund === 'keine_stufe'}
            <a href="/teaching" class="flex-shrink-0 text-light-bl dark:text-dark-bl hover:underline">Zu Unterricht</a>
        {/if}
    </div>
{/if}
