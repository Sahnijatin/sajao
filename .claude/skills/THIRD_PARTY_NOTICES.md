# Third-party skills

These skill folders are copied unchanged from their upstream repositories so they load in every session, including cloud sessions. Each is MIT licensed; the license file sits in the skill's folder where upstream ships one.

| Skill folders | Upstream | Commit | License |
| --- | --- | --- | --- |
| karpathy-guidelines | github.com/multica-ai/andrej-karpathy-skills | 2c60614 | MIT (stated in the upstream README and SKILL.md) |
| supabase, supabase-postgres-best-practices | github.com/supabase/agent-skills | c9be0e9 | MIT, Copyright (c) 2026 Supabase |
| react-native-best-practices | github.com/callstackincubator/agent-skills | 59e9d17 | MIT, Copyright (c) 2026 Callstack Incubator |
| expo-overview, expo-router, expo-animation, expo-native-ui, expo-ui, expo-data-fetching, expo-dev-client, expo-project-structure, expo-upgrade, eas-update, eas-workflows, eas-app-stores | github.com/expo/skills | ab6cb2c | MIT, Copyright (c) 2025-present 650 Industries, Inc. (aka Expo) |

Changes made when copying: the `references/images` folder of react-native-best-practices was left out to keep the repository small; text references to those images remain.

To update a skill, copy the upstream folder again at a newer commit, keep its license file, and update this table.
