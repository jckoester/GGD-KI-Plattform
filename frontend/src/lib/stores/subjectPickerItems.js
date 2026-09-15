import { derived } from 'svelte/store'
import { subjectMap } from './subjects.js'
import { aktuelleTeachingGroups, myGroups, myTeachingGroups } from './myGroups.js'

/**
 * Schüler: flache Liste mit Fach-Alias (teaching_group → Fachname).
 * Bei mehreren Gruppen desselben Fachs: qualifizierender Gruppenname-Zusatz.
 * Jedes Item: { type: 'group', id, subjectId, label, color }
 *
 * **Bewusst alle Gruppen, nicht nur die aktuellen** (AP8 Schritt 2, 15.09.2026). Für eine
 * Schüler:in *ist* die Gruppe das Fach — fiele sie hier heraus, ließe sich das Fach nicht
 * mehr anwählen. Bei Lehrkräften ist eine zu viel gezeigte Gruppe Unordnung, hier wäre
 * eine zu wenig gezeigte ein Ausfall. Die Gruppen von Schüler:innen stammen ohnehin aus
 * dem Schulkonto (immer aktuell) oder werden über die Klasse vererbt — und die
 * Klassenzugehörigkeit endet mit dem Schuljahr von selbst.
 */
export const studentPickerItems = derived(
  [myTeachingGroups, subjectMap],
  ([$myTeachingGroups, $subjectMap]) => {
    const countPerSubject = {}
    for (const g of $myTeachingGroups) {
      countPerSubject[g.subject_id] = (countPerSubject[g.subject_id] ?? 0) + 1
    }
    return $myTeachingGroups.map(g => ({
      type: 'group',
      id: g.id,
      subjectId: g.subject_id,
      label: countPerSubject[g.subject_id] > 1
        ? `${$subjectMap[g.subject_id]?.name ?? g.name} · ${g.name}`
        : ($subjectMap[g.subject_id]?.name ?? g.name),
      color: $subjectMap[g.subject_id]?.color ?? null,
    }))
  }
)

/**
 * Lehrkraft: Fächer mit eingerückten Unterrichtsgruppen.
 * Fächer: { type: 'subject', id, label, color }
 * Gruppen: { type: 'group', id, subjectId, label, color }
 *
 * Nur die Gruppen des laufenden Schuljahres: Wer hier eine frühere wählte, schriebe seinen
 * Chat in ein vergangenes Schuljahr. Die **Fächer** kommen weiter aus allen Gruppen — ein
 * Fach verschwindet nicht, nur weil dieses Jahr noch keine Gruppe darin Belege hat.
 */
export const teacherPickerItems = derived(
  [myGroups, aktuelleTeachingGroups, subjectMap],
  ([$myGroups, $myTeachingGroups, $subjectMap]) => {
    const allSubjectIds = [...new Set(
      $myGroups
        .filter(g => g.subject_id != null)
        .map(g => g.subject_id)
    )]
    const sortedSubjects = allSubjectIds
      .map(id => $subjectMap[id])
      .filter(Boolean)
      .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0))

    const items = []
    for (const subj of sortedSubjects) {
      items.push({ type: 'subject', id: subj.id, label: subj.name, color: subj.color })
      for (const g of $myTeachingGroups.filter(g => g.subject_id === subj.id)) {
        items.push({ type: 'group', id: g.id, subjectId: subj.id, label: g.name, color: subj.color })
      }
    }
    return items
  }
)
