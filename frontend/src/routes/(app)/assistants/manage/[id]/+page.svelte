<script>
  import AssistantEditor from "$lib/components/AssistantEditor.svelte";
  let { data } = $props();
</script>

<AssistantEditor
  assistantId={data.id}
  isAdmin={true}
  backUrl="/assistants/manage"
/>
