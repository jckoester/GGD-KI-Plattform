import { derived } from 'svelte/store'
import { subjectMap } from './subjects.js'
import { myGroups, myTeachingGroups } from './myGroups.js'

/**
 * Schüler: flache Liste mit Fach-Alias (teaching_group → Fachname).
 * Bei mehreren Gruppen desselben Fachs: qualifizierender Gruppenname-Zusatz.
 * Jedes Item: { type: 'group', id, subjectId, label, color }
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
 */
export const teacherPickerItems = derived(
  [myGroups, myTeachingGroups, subjectMap],
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
