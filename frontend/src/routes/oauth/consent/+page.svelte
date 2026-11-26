<script>
    // Zustimmung zu einem KI-Programm (0.55, Päckchen AX Schritt 4). Hierher schickt der
    // Autorisierungsserver den Browser nach `/api/authorize`. Ohne Sitzung zur Anmeldung und
    // zurück; danach entscheidet die Lehrkraft, und der Browser geht an das Programm zurück.
    import { onMount } from "svelte";
    import { ShieldCheck } from "@lucide/svelte";
    import { getOAuthAnfrage, sendOAuthEntscheidung } from "$lib/api.js";
    import { anfrageAusUrl, anmeldeZiel, fehlerText } from "$lib/oauth_zustimmung.js";
    import ErrorBanner from "$lib/components/ErrorBanner.svelte";
    import LoadingBanner from "$lib/components/LoadingBanner.svelte";

    let anfrage = $state(null);
    let info = $state(null);
    let fehler = $state("");
    let sendet = $state(false);

    onMount(async () => {
        anfrage = anfrageAusUrl(window.location.search);
        if (!anfrage) {
            fehler = "Diese Seite braucht eine Anfrage aus einem KI-Programm. Bitte im Programm neu verbinden.";
            return;
        }
        try {
            info = await getOAuthAnfrage(anfrage);
        } catch (e) {
            if (e.status === 401) {
                window.location.href = anmeldeZiel(anfrage);
                return;
            }
            fehler = fehlerText(e.status, e.message);
        }
    });

    async function entscheiden(zulassen) {
        sendet = true;
        fehler = "";
        try {
            const { weiter } = await sendOAuthEntscheidung(anfrage, zulassen);
            window.location.href = weiter;
        } catch (e) {
            fehler = fehlerText(e.status, e.message);
            sendet = false;
        }
    }
</script>

<svelte:head>
    <title>KI-Programm verbinden</title>
</svelte:head>

<div class="min-h-dvh bg-light-bg-2 dark:bg-dark-bg flex flex-col items-center justify-center p-4">
    <div class="bg-light-bg dark:bg-dark-ui rounded-2xl shadow-lg w-full max-w-md p-8 space-y-5">
        <div class="flex items-center gap-3">
            <ShieldCheck class="w-7 h-7 text-light-bl dark:text-dark-bl shrink-0" />
            <h1 class="text-xl font-semibold text-light-tx dark:text-dark-tx">KI-Programm verbinden</h1>
        </div>

        {#if fehler}
            <ErrorBanner message={fehler} />
        {:else if !info}
            <LoadingBanner />
        {:else}
            <p class="text-light-tx dark:text-dark-tx">
                <strong>{info.programm}</strong> möchte auf die Plattform zugreifen.
            </p>
            <dl class="text-sm space-y-2">
                <div>
                    <dt class="text-light-tx-2 dark:text-dark-tx-2">Berechtigung</dt>
                    <dd class="text-light-tx dark:text-dark-tx">{info.berechtigung} — nur lesen, nichts ändern</dd>
                </div>
                <div>
                    <dt class="text-light-tx-2 dark:text-dark-tx-2">Zurück an</dt>
                    <dd class="text-light-tx dark:text-dark-tx"><code class="break-all">{info.ruecksprung}</code></dd>
                </div>
                <div>
                    <dt class="text-light-tx-2 dark:text-dark-tx-2">Dauer</dt>
                    <dd class="text-light-tx dark:text-dark-tx">
                        {info.tage} Tage; beenden kannst du die Verbindung jederzeit im Profil unter „Zugangstoken“.
                    </dd>
                </div>
            </dl>
            <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
                Was das Programm liest, geht an seinen Anbieter. Lass nur zu, wenn du die Verbindung
                gerade selbst angestoßen hast und den Rücksprung-Host kennst.
            </p>
            <div class="flex justify-end gap-3 pt-2">
                <button
                    type="button"
                    disabled={sendet}
                    onclick={() => entscheiden(false)}
                    class="px-4 py-2 rounded-lg border border-light-ui-3 dark:border-dark-ui-3
                           text-light-tx dark:text-dark-tx hover:bg-light-bg-2 dark:hover:bg-dark-bg-2
                           disabled:opacity-50"
                >Ablehnen</button>
                <button
                    type="button"
                    disabled={sendet}
                    onclick={() => entscheiden(true)}
                    class="px-4 py-2 rounded-lg bg-primary dark:bg-primary-dark text-on-fill
                           hover:opacity-90 disabled:opacity-50"
                >Zulassen</button>
            </div>
        {/if}
    </div>
</div>
