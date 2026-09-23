<script>
  /**
   * Einer Unterrichtsgruppe per Code beitreten (AP4).
   *
   * Für Kurse der Kursstufe, Teilgruppen und Nachzügler — überall dort, wo die
   * Gruppe ihre Mitglieder nicht aus einer Klasse erbt. Ohne diesen Weg käme in solche
   * Gruppen niemand hinein: Namen zeigt die Plattform nicht, eine Mitgliederliste wäre
   * also nicht bedienbar.
   */
  import { LogIn } from "lucide-svelte"
  import { invalidateAll } from "$app/navigation"
  import { joinGroupByCode } from "$lib/api.js"
  import { beitrittFehler } from "$lib/beitrittscode.js"
  import ErrorBanner from "$lib/components/ErrorBanner.svelte"
  import SuccessBanner from "$lib/components/SuccessBanner.svelte"

  let eingabe = $state("")
  let arbeitet = $state(false)
  let fehler = $state(null)
  let erfolg = $state(null)

  async function beitreten(ev) {
    ev.preventDefault()
    if (!eingabe.trim()) return
    arbeitet = true
    fehler = null
    erfolg = null
    try {
      await joinGroupByCode(eingabe.trim())
      erfolg = "Du bist der Gruppe beigetreten."
      eingabe = ""
      // Neu laden statt lokal ergänzen: Welches Fach die Gruppe trägt und ob sie
      // sichtbar ist, entscheidet der Server — hier zu raten ginge schief.
      await invalidateAll()
    } catch (e) {
      fehler = beitrittFehler(e.message)
    } finally {
      arbeitet = false
    }
  }
</script>

<form onsubmit={beitreten} class="mt-6 max-w-md">
  <label
    for="beitrittscode"
    class="block text-sm font-medium text-light-tx dark:text-dark-tx"
  >
    Einer Gruppe beitreten
  </label>
  <p class="mt-0.5 text-xs text-light-tx-2 dark:text-dark-tx-2">
    Mit dem Code, den du im Unterricht bekommen hast.
  </p>

  <div class="mt-2 flex gap-2">
    <input
      id="beitrittscode"
      bind:value={eingabe}
      placeholder="ABCD-EFGH"
      autocomplete="off"
      autocapitalize="characters"
      spellcheck="false"
      class="flex-1 rounded-md border border-light-ui-3 dark:border-dark-ui-3
             bg-light-bg dark:bg-dark-bg px-3 py-1.5 font-mono tracking-widest
             text-light-tx dark:text-dark-tx"
    />
    <button
      type="submit"
      disabled={arbeitet || !eingabe.trim()}
      class="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium
             bg-primary dark:bg-primary-dark text-white disabled:opacity-50"
    >
      <LogIn size={15} />
      {arbeitet ? "…" : "Beitreten"}
    </button>
  </div>

  {#if fehler}<div class="mt-2"><ErrorBanner message={fehler} /></div>{/if}
  {#if erfolg}<div class="mt-2"><SuccessBanner message={erfolg} /></div>{/if}
</form>
