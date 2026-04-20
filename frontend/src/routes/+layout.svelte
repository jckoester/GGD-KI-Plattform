<script>
  import './layout.css'
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
