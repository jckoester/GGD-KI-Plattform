<script>
  import './layout.css'
  import 'katex/dist/katex.min.css' // Mathe-/Chemie-Rendering (Phase 15)
  // Markierte Formeln als LaTeX kopieren statt als Zeichensalat (0.12). Meldet sich
  // global am Dokument an — deshalb hier und nicht in markdown.js, das auch Tests ohne
  // DOM laden.
  import 'katex/contrib/copy-tex'
  import { onMount } from 'svelte'
  import { themePref } from '$lib/stores/theme.js'

  const { children } = $props()

  let currentPref = 'system'

  function applyTheme(pref) {
    currentPref = pref
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
    const dark = pref === 'dark' || (pref === 'system' && prefersDark)
    document.documentElement.classList.toggle('dark', dark)
  }

  onMount(() => {
    const unsub = themePref.subscribe(applyTheme)

    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const mqHandler = () => applyTheme(currentPref)
    mq.addEventListener('change', mqHandler)

    // Initial anwenden
    applyTheme($themePref)

    return () => {
      unsub()
      mq.removeEventListener('change', mqHandler)
    }
  })
</script>

{@render children()}
