---
name: web
display_name: web
display_name_zh: 网页模式
description: "Use this skill when the user wants a web page, marketing page, homepage, promo page, small site, or frontend section created or updated inside the current workspace. This skill is for harness-native web work: inspecting the existing repo first, matching the current stack when one exists, generating HTML/CSS/JS or React/Next.js code that fits the project, and using harness-native tools correctly."
description_zh: "当用户希望在当前工作区中创建或更新网页、营销页、首页、宣传页、小型站点或前端页面片段时使用此技能。它适用于 harness 原生网页工作流：先检查现有仓库，再匹配当前技术栈，生成符合项目的 HTML/CSS/JS 或 React/Next.js 代码，并正确使用 harness 原生工具。"
od:
  category: web-surface
  mode: prototype
  surface: web
  scenario: marketing
  featured: 2
  design_system:
    requires: true
    sections:
      - Color
      - Typography
      - Components
  craft:
    requires:
      - visual-hierarchy
      - responsive-rhythm
tools:
  - exec_command
  - list_files
  - read_file
  - edit_file
  - write_file
  - workspace_map
  - register_artifact
  - publish_output
  - analyze_image
  - generate_image
  - generate_video
  - Agent
  - web_search
name_zh: 网页模式
---

# Web Skill

Follow the harness workspace contract.

## What This Skill Is For

Use this skill when the user asks for:

- a homepage or marketing page
- a promo or campaign page
- a small website or static page
- a new frontend section in an existing app
- a redesign of an existing web page

Do not assume Next.js, React, or Tailwind unless the repository already uses them. First inspect the repository and preserve the existing stack, routing model, styling approach, and component conventions.

## Required Workflow

1. Inspect the current workspace before proposing or generating code.
2. Detect the actual stack: framework, routing, styling, components, and build commands.
3. Choose the narrowest change that fits the repository.
4. Preserve existing conventions if the project already has them.
5. If there is no existing web stack, choose the simplest deliverable that satisfies the request.
6. Verify with the repo's available checks.

## Design Rules

- Make the page feel intentional, not boilerplate.
- Optimize for clear hierarchy, responsive layout, and accessible contrast.
- Use real copy when the user gives enough context; otherwise write plausible draft copy, not lorem ipsum.
- Match the repo's design system when one exists.
- If no design system exists, use restrained styling and consistent spacing.
- Keep simple pages lightweight.

## References

Read these local references only when useful:

- `references/conversion-patterns.md`
- `references/copy-frameworks.md`
- `references/seo-checklist.md`

## Final Checks

Before finishing, confirm the output matches the repo stack, mobile layout is reasonable, headings and navigation are internally consistent, and relevant build/test/lint commands have been run when available.
