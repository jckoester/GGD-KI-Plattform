import { derived } from 'svelte/store'
import { subjectMap } from './subjects.js'
import { myGroups, myTeachingGroups } from './myGroups.js'
import { conversationCountsByGroup } from './conversationCounts.js'
import { assistantSubjectIds } from './assistants.js'
import { user } from './user.js'
import { potentialTeachingGroups } from './potentialTeachingGroups.js'

export const sidebarSubjectSections = derived(
  [user, subjectMap, myGroups, myTeachingGroups, conversationCountsByGroup, assistantSubjectIds, potentialTeachingGroups],
  ([$user, $subjectMap, $myGroups, $myTeachingGroups, $byGroup, $assistantSubjectIds, $potential]) => {
    if (!$user) return []

    const isTeacher = $user.roles?.includes('teacher')

    if (isTeacher) {
      // Lehrkraft: Fächer aus teaching_groups UND subject_department-Gruppen
      const teachingSubjectIds = $myTeachingGroups.map(g => g.subject_id).filter(Boolean)
      const deptSubjectIds = $myGroups
        .filter(g => g.type === 'subject_department' && g.subject_id != null)
        .map(g => g.subject_id)
      const subjectIds = [...new Set([...teachingSubjectIds, ...deptSubjectIds])]
      if (subjectIds.length === 0) return []
      return subjectIds
        .map(id => $subjectMap[id])
        .filter(Boolean)
        .sort((a, b) => (a.sort_order ?? 999) - (b.sort_order ?? 999))
        .map(subj => ({
          type: 'teacher',
          subjectId: subj.id,
          name: subj.name,
          icon: subj.icon ?? null,
          color: subj.color ?? null,
          slug: subj.slug,
          groups: $myTeachingGroups
            .filter(g => g.subject_id === subj.id)
            .map(g => ({
              groupId: g.id,
              name: g.name,
              count: parseInt($byGroup[String(g.id)] ?? 0),
              isManual: !g.sso_group_id,  // für Lösch-Button
            })),
          potentialGroups: $potential
            .filter(p => p.subject_id === subj.id)
            .map(p => ({
              classGroupId: p.class_group_id,
              className: p.class_name,
              subjectId: p.subject_id,
            })),
        }))
    } else {
      // Schüler:in: flache Fach-Liste (teaching_groups als Fach-Aliase)
      const countPerSubject = {}
      for (const g of $myTeachingGroups) {
        if (g.subject_id != null)
          countPerSubject[g.subject_id] = (countPerSubject[g.subject_id] ?? 0) + 1
      }
      return $myTeachingGroups
        .map(g => {
          const subj = $subjectMap[g.subject_id]
          const count = parseInt($byGroup[String(g.id)] ?? 0)
          const hasAssistant = $assistantSubjectIds.has(g.subject_id)
          // Sichtbarkeitsregel: mind. 1 Chat ODER mind. 1 Assistent verfügbar
          if (count === 0 && !hasAssistant) return null
          return {
            type: 'student',
            subjectId: g.subject_id,
            name: subj?.name ?? g.name,
            icon: subj?.icon ?? null,
            color: subj?.color ?? null,
            slug: subj?.slug ?? null,
            groupId: g.id,
            qualifier: countPerSubject[g.subject_id] > 1 ? g.name : null,
            count,
          }
        })
        .filter(Boolean)
    }
  }
)
