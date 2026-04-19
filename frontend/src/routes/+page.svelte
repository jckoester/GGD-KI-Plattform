<script>
  import { onMount } from 'svelte'
  import { goto } from '$app/navigation'
  import { login, getMe } from '$lib/api.js'
  import { branding } from '$lib/branding.js'

  let username = ''
  let password = ''
  let error = ''
  let loading = false
  let challenge = { type: 'form', redirect_url: null }

  onMount(async () => {
    try { await getMe(); goto('/hello'); return } catch { /* weiter */ }

    try {
      const res = await fetch('/api/auth/login-challenge')
      if (res.ok) challenge = await res.json()
    } catch { /* Standardwert: form */ }
  })

  async function handleSubmit() {
    error = ''
    loading = true
    try {
      await login(username, password)
      goto('/hello')
    } catch (e) {
      error = e.message
    } finally {
      loading = false
    }
  }

  const initials = (name) => name.slice(0, 2).toUpperCase()
</script>

<div class="min-h-screen bg-gray-100 flex items-center justify-center p-4">
  <div class="bg-white rounded-2xl shadow-lg w-full max-w-sm p-8 space-y-6">

    <div class="flex flex-col items-center gap-2">
      {#if branding.logo_url}
        <img src={branding.logo_url} alt="Logo" class="h-16 w-auto" />
      {:else}
        <div class="w-14 h-14 rounded-full bg-primary flex items-center justify-center
                    text-white text-xl font-bold select-none">
          {initials(branding.name)}
        </div>
      {/if}
      <h1 class="text-2xl font-semibold text-gray-800">{branding.name}</h1>
    </div>

    {#if challenge.type === 'redirect'}
      <a href={challenge.redirect_url}
         class="block w-full text-center py-2.5 px-4 rounded-lg bg-primary
                hover:bg-primary-dark text-white font-medium transition-colors">
        Anmelden mit IServ
      </a>
    {:else}
      <form onsubmit={(e) => { e.preventDefault(); handleSubmit() }} class="space-y-4">
        <div class="space-y-1">
          <label for="username" class="block text-sm font-medium text-gray-700">
            Benutzername
          </label>
          <input id="username" type="text" bind:value={username} required
                 class="w-full rounded-lg border-gray-300 focus:border-primary
                        focus:ring-primary" />
        </div>
        <div class="space-y-1">
          <label for="password" class="block text-sm font-medium text-gray-700">
            Passwort
          </label>
          <input id="password" type="password" bind:value={password} required
                 class="w-full rounded-lg border-gray-300 focus:border-primary
                        focus:ring-primary" />
        </div>
        {#if error}
          <p class="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>
        {/if}
        <button type="submit" disabled={loading}
                class="w-full py-2.5 px-4 rounded-lg bg-primary hover:bg-primary-dark
                       text-white font-medium transition-colors disabled:opacity-50
                       disabled:cursor-not-allowed">
          {loading ? 'Bitte warten…' : 'Anmelden'}
        </button>
      </form>
    {/if}

  </div>
</div>
