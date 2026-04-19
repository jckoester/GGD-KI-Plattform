<script>
  import { onMount } from 'svelte'
  import { goto } from '$app/navigation'
  import { login, getMe } from '$lib/api.js'

  let username = ''
  let password = ''
  let error = ''
  let loading = false

  onMount(async () => {
    try {
      await getMe()
      goto('/hello')
    } catch {
      // nicht angemeldet — Login-Formular zeigen
    }
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
</script>

<h1>Anmelden</h1>

<form on:submit|preventDefault={handleSubmit}>
  <div>
    <label for="username">Benutzername</label>
    <input id="username" type="text" bind:value={username} required />
  </div>
  <div>
    <label for="password">Passwort</label>
    <input id="password" type="password" bind:value={password} required />
  </div>
  {#if error}
    <p>{error}</p>
  {/if}
  <button type="submit" disabled={loading}>
    {loading ? 'Bitte warten…' : 'Anmelden'}
  </button>
</form>
