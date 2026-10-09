# shared

Building blocks any project may use: generic agents, prompts, tools and schemas with no project-specific meaning.

- Never reference anything under `projects/` from here.
- Move something here once a second project needs it, instead of copying it.
- Changes here affect every project that uses them, so keep them backward compatible or update the users in the same change.
