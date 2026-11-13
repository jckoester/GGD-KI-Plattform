<script>
    // Eine Leiste für alles, was aus einer Antwort ein Produkt werden kann (0.41, Schritt 7):
    // Bild, Diagramm und Text. Bis dahin baute der Chat drei verschiedene Leisten — mit
    // verschiedenen Wörtern für dasselbe. Reihenfolge immer: Speichern · Als Dokument
    // bearbeiten · Herunterladen · Weiteres der Art · Als Baustein speichern.
    //
    // `variante`: „overlay“ liegt über Bild oder Diagramm (erscheint beim Überfahren),
    // „zeile“ steht unter einer Textantwort.
    import { BookmarkPlus, Check, FileEdit, Download, Share2, Loader2, AlertCircle } from 'lucide-svelte'
    import { speicherText } from '$lib/produktleiste.js'

    let {
        variante = 'overlay',
        speichern = null,        // async () => { created }
        bearbeiten = null,       // async () => void — nur Text (Diagramme ab Päckchen L)
        herunterladen = null,    // { href, dateiname } | async () => void
        extras = [],             // [{ id, label, titel, aktion: async () => string | void }]
        alsBaustein = null,      // async () => void
        hinweis = null,          // Satz unter der Zeile (etwa: Text mit Bildern)
        onGespeichert = null,    // (created) => void
    } = $props()

    let zustand = $state('idle')   // idle | saving | saved | exists | full | error
    let laeuft = $state(null)      // id der gerade laufenden Aktion
    let rueckmeldung = $state({})  // id → kurzer Text nach einer Aktion
    let fehler = $state(null)

    async function speichernKlick() {
        if (zustand === 'saving') return
        zustand = 'saving'
        try {
            const r = await speichern()
            zustand = r?.created === false ? 'exists' : 'saved'
            onGespeichert?.(r?.created !== false)
        } catch (e) {
            zustand = e?.status === 409 ? 'full' : 'error'
            setTimeout(() => { zustand = 'idle' }, 2500)
        }
    }

    async function ausfuehren(id, aktion, fehlertext) {
        if (laeuft) return
        laeuft = id
        fehler = null
        try {
            const text = await aktion()
            if (text) {
                rueckmeldung = { ...rueckmeldung, [id]: text }
                setTimeout(() => { rueckmeldung = { ...rueckmeldung, [id]: null } }, 1800)
            }
        } catch (e) {
            fehler = e?.status === 409 ? 'Werkstatt voll — bitte zuerst aufräumen.' : fehlertext
        } finally {
            laeuft = null
        }
    }

    const knopf = $derived(variante === 'overlay'
        ? 'inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs bg-light-bg-2/90 dark:bg-dark-bg-2/90 text-light-tx-2 dark:text-dark-tx-2 hover:bg-light-ui-3 dark:hover:bg-dark-ui-3 disabled:opacity-60'
        : 'inline-flex items-center gap-1 text-xs px-2 py-1 rounded text-light-tx-2 dark:text-dark-tx-2 hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors disabled:opacity-50')
</script>

<div class={variante === 'overlay' ? 'flex flex-wrap gap-1' : 'flex flex-wrap items-center gap-1'}>
    {#if speichern}
        <button
            type="button"
            onclick={speichernKlick}
            disabled={zustand === 'saving'}
            title={speicherText(zustand, 'titel')}
            aria-label={speicherText(zustand, 'titel')}
            class={knopf}
        >
            {#if zustand === 'saving'}
                <Loader2 class="w-3.5 h-3.5 animate-spin" />
            {:else if zustand === 'saved' || zustand === 'exists'}
                <Check class="w-3.5 h-3.5" />
            {:else if zustand === 'full' || zustand === 'error'}
                <AlertCircle class="w-3.5 h-3.5" />
            {:else}
                <BookmarkPlus class="w-3.5 h-3.5" />
            {/if}
            {speicherText(zustand, 'knopf')}
        </button>
    {/if}
    {#if bearbeiten}
        <button
            type="button"
            onclick={() => ausfuehren('bearbeiten', bearbeiten, 'Konnte nicht als Dokument angelegt werden.')}
            disabled={laeuft === 'bearbeiten'}
            title={hinweis ?? undefined}
            class={knopf}
        >
            <FileEdit class="w-3.5 h-3.5" />
            {laeuft === 'bearbeiten' ? 'Wird geöffnet…' : 'Als Dokument bearbeiten'}
        </button>
    {/if}
    {#if herunterladen}
        {#if herunterladen.href}
            <a href={herunterladen.href} download={herunterladen.dateiname} class={knopf} title="Herunterladen">
                <Download class="w-3.5 h-3.5" /> Herunterladen
            </a>
        {:else}
            <button
                type="button"
                onclick={() => ausfuehren('herunterladen', herunterladen, 'Herunterladen fehlgeschlagen.')}
                disabled={laeuft === 'herunterladen'}
                title="Herunterladen"
                class={knopf}
            >
                <Download class="w-3.5 h-3.5" /> {rueckmeldung.herunterladen ?? 'Herunterladen'}
            </button>
        {/if}
    {/if}
    {#each extras as ex (ex.id)}
        <button
            type="button"
            onclick={() => ausfuehren(ex.id, ex.aktion, 'Das hat nicht geklappt.')}
            disabled={laeuft === ex.id}
            title={ex.titel}
            aria-label={ex.titel}
            class={knopf}
        >
            {rueckmeldung[ex.id] ?? ex.label}
        </button>
    {/each}
    {#if alsBaustein}
        <!-- Die Werkstatt ist zum Weiterschreiben da, der Baustein zum Wiederfinden — zwei
             Absichten, zwei Knöpfe (AP8). -->
        <button
            type="button"
            onclick={() => ausfuehren('baustein', alsBaustein, 'Konnte nicht als Baustein gespeichert werden.')}
            disabled={laeuft === 'baustein'}
            title={hinweis ?? undefined}
            class={knopf}
        >
            <Share2 class="w-3.5 h-3.5" />
            {laeuft === 'baustein' ? 'Wird vorbereitet…' : 'Als Baustein speichern'}
        </button>
    {/if}
    {#if variante === 'zeile' && (zustand === 'saved' || zustand === 'exists')}
        <a href="/workshop" class="text-xs text-light-bl dark:text-dark-bl hover:underline">In der Werkstatt ✓</a>
    {/if}
    {#if variante === 'zeile' && hinweis}
        <p class="w-full text-xs text-light-tx-2 dark:text-dark-tx-2 mt-0.5">{hinweis}</p>
    {/if}
    {#if fehler}
        <p class="w-full text-xs text-light-re dark:text-dark-re mt-0.5">{fehler}</p>
    {/if}
</div>
