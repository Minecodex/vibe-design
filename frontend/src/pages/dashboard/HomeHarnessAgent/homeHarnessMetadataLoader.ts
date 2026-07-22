import {
  agentApi,
  type HarnessDesignSystemRead,
  type HarnessSkillRead,
} from '@/api/endpoints/agent'

interface HomeHarnessMetadata {
  skills: HarnessSkillRead[]
  designSystems: HarnessDesignSystemRead[]
}

let homeHarnessMetadataRequest: Promise<HomeHarnessMetadata> | null = null

export async function loadHomeHarnessMetadata(): Promise<HomeHarnessMetadata> {
  if (homeHarnessMetadataRequest) {
    return homeHarnessMetadataRequest
  }

  homeHarnessMetadataRequest = (async () => {
    const [skillsRes, designSystemsRes] = await Promise.all([
      agentApi.listHarnessSkills(),
      agentApi.listHarnessDesignSystems(),
    ])

    return {
      skills: skillsRes.data,
      designSystems: designSystemsRes.data,
    }
  })().finally(() => {
    homeHarnessMetadataRequest = null
  })

  return homeHarnessMetadataRequest
}

export const __homeHarnessMetadataLoaderTestUtils = {
  reset() {
    homeHarnessMetadataRequest = null
  },
}
