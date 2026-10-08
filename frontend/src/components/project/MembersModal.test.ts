import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

const currentDir = dirname(fileURLToPath(import.meta.url))
const membersModalSource = readFileSync(resolve(currentDir, 'MembersModal.tsx'), 'utf8')
const projectsPageSource = readFileSync(resolve(currentDir, '../../pages/dashboard/ProjectsPage/index.tsx'), 'utf8')

describe('MembersModal owner protections', () => {
  it('uses add-user wording for the member search area and feedback', () => {
    expect(membersModalSource).toContain("t('projectsPage.addMember')")
    expect(membersModalSource).toContain("t('projectsPage.addMemberPlaceholder')")
    expect(membersModalSource).toContain("t('projectsPage.memberAddSuccess')")
  })

  it('uses fuzzy member search instead of exact-match lookup', () => {
    expect(membersModalSource).toContain('usersApi.search(value)')
    expect(membersModalSource).not.toContain('usersApi.searchExact(value)')
  })

  it('does not render the delete action for the project owner', () => {
    expect(membersModalSource).toContain('item.user_id !== ownerUserId && (')
  })

  it('blocks removing the project owner in the delete handler', () => {
    expect(membersModalSource).toContain('if (userId === ownerUserId) {')
  })

  it('receives the project owner id from the projects page', () => {
    expect(projectsPageSource).toContain('ownerUserId={selectedProject.user_id}')
  })
})
