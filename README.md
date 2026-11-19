# AI Design

<p align="center"><strong>Tell the agent what site you want — and see it before it is built.</strong></p>

<p align="center"><b>English</b> · <a href="README.ru.md">Русский</a></p>

AI Design is a front-end design skill. It looks at your references, interviews you about taste, style and tone, shows **three live previews** on a panel, repeats the rounds until one feels right, and only then builds the page. At the end it leaves written design rules, so any later agent continues in the same style. The goal is a site that does not look like every other AI-made site.

It works on its own: whatever is missing on the computer it names and installs itself, after your «yes». It works on an empty folder (a new site, a landing page, a block, a web-app screen, an HTML presentation) and on a site that already exists (a redesign that does not break it). Before the first edit it makes a copy of the project, keeps the style in one folder `design-system/` that you can hand to another person, and on request shows a large site in Figma.

The family: [AISpa](https://github.com/alexfisenkov/aispa) — builds whole projects from a description · [AI Мастерская](https://github.com/alexfisenkov/aimaster) — the workshop's skill pack · [AIEditing](https://github.com/alexfisenkov/AIEditing) — video editing.

<p align="center">
  <img src="assets/panel-en.png" width="640" alt="The panel: stages, the current round with three live previews, round history, interview topics">
</p>

<p align="center"><sub>The panel during a run: seven stages, the current round with three live previews you can enlarge, the history of rounds, the interview topics.</sub></p>

---

## From scratch: nothing on the computer yet

If you have neither an agent nor Node.js yet — four steps. Everything else (Python, git, a browser for checking, ffmpeg for video) the skill finds and installs itself, asking once.

1. **The agent.** Install the Claude app and open its Code tab — [claude.com/download](https://claude.com/download) — or Codex — [developers.openai.com/codex](https://developers.openai.com/codex).
2. **Node.js LTS** (for the `npx` command). The easiest is the LTS installer from [nodejs.org](https://nodejs.org/en/download). Or one command in the Terminal:

   | System | Command |
   |---|---|
   | Mac (with Homebrew) | `brew install node` |
   | Windows | `winget install OpenJS.NodeJS.LTS` |
   | Linux | `sudo apt install nodejs npm` (Fedora — `sudo dnf install nodejs npm`) |

   You need version 22 or newer (`node --version`). On Linux the system package can be older — then install the current LTS from [nodejs.org](https://nodejs.org/en/download); the skill will also say «нужно обновить» (needs an update).

   If a password is asked, you type it into your own Terminal — never into the chat with the agent.
3. **The skill:** `npx skills add alexfisenkov/aidesign --skill aidesign -g -y -a claude-code codex` (details below, in «Installation»). Restart the agent.
4. **First run:** open the agent in the folder of the future site and type «run /aidesign» (in Codex — `$aidesign`). The skill first checks for Python and, if it is missing, gives one command for your system.

### Without Node.js

Download the archive of the latest release from the [releases](https://github.com/alexfisenkov/aidesign/releases) page, unpack it and put the `skills/aidesign` folder into the agent's skills folder:

| Agent | Where to put it |
|---|---|
| Claude Code | `~/.claude/skills/aidesign` (Windows: `%USERPROFILE%\.claude\skills\aidesign`) |
| Codex | `~/.agents/skills/aidesign` (older Codex versions — `~/.codex/skills/aidesign`) |

Restart the agent. Update the same way: a new archive over the old folder.

---

## Installation

### If you'd rather not open a terminal

Open your AI agent — Claude Code or Codex — and paste this:

```
Install the AI Design skill for me. Run in the terminal:

npx skills add alexfisenkov/aidesign --skill aidesign -g -y -a claude-code codex

If npx is not found, give me a link to download Node.js and wait.
Don't install anything else.
When you're done, tell me in one line that it's ready and that the session needs a restart.
```

The agent does the rest. Then restart it — skills are loaded at startup.

### From the terminal

```bash
npx skills add alexfisenkov/aidesign --skill aidesign -g -y -a claude-code codex
```

| Flag | What it does |
|------|--------------|
| `--skill aidesign` | Installs only AI Design |
| `-a claude-code codex` | For Claude Code and Codex (other agents — name them instead) |
| `-g` | Globally — the skill is available in every project |
| `-y` | Don't ask questions |

**Requires:** [Node.js](https://nodejs.org) (for `npx`), Python 3.9+ (the panel and the checks use only its standard library) and any supported AI agent. The rest — git, the Chromium browser through Playwright for screenshots, ffmpeg for video — the skill checks at the start of a run and installs with official commands after your «yes».

**Equipping the agent** means only programs on the computer plus Figma MCP if you want it: the browser for checking is Playwright from the command line, with no separate MCP; AI Design installs no other MCPs or skills.

**Update:** `npx skills update aidesign -g`, then restart the session. At the start of a run the skill compares its version with this repository and tells you in one line if a new one is out; it never updates in the middle of a run. To turn the check off: the environment variable `AIDESIGN_NO_UPDATE_CHECK=1`.

---

## How to use it

Open your agent in the folder of the future site and type:

```
/aidesign a landing page for a small bookbinding workshop
```

In Codex the command is `$aidesign`. A bare `/aidesign` resumes an interrupted run.

Name the mode in the command or the agent asks one question first:

| Mode | How to turn it on | What you're asked |
|---|---|---|
| **On my own from the brief** (`auto`) | `/aidesign auto ...` | Almost nothing: three previews from your description and references; you only choose |
| **Only what matters** (`important`) | `/aidesign important ...` | The 5–10 main things about taste; the rest is decided for you |
| **Interview** (`interview`) | `/aidesign interview ...` | A detailed talk, topic by topic, with the agent's own answer to every question. Say «по одному» for one question per message |

Questions that really change the look are marked ⚑ with options а/б/в — that letter you pick yourself. For the rest «ок» is enough, and «дальше решай сам» closes the interview at any moment.

### The seven stages

| Stage | What happens |
|---|---|
| **Preparation** | Is Python there and what else the computer needs (one question about installing), mode, entry (new or existing site), the panel opens by itself, the project laid out in folders |
| **References** | You show images, screenshots or links; the agent writes down what you like in each |
| **Interview** | Questions about the audience, character, tone, density, colour, type, motion |
| **Previews** | Three truly different first screens, live; you click, choose, say what to change; round after round until it feels right |
| **Build** | First a copy of the project, then the design system, then the real pages; the agent reads the knowledge it needs for your case |
| **Check** | A script catches the marks of template design (49 rules), a second one catches style that bypasses the design system; screenshots on phone and desktop; found problems are fixed |
| **Handoff** | `DESIGN.md`, the design system, a block of rules in the project memory, the «after» copy; a short report; Figma if the site is large and you want it |

### The panel

At the start the agent opens a panel — a page you never have to find or launch. It shows the stage, working time, your references, the interview topics, the **current round** with three live miniatures (click one: full screen, a switch between desktop and phone, arrows between variants), the history of rounds with your feedback, the chosen direction, the check result and a feed of events. A tab **Examples** shows seven finished demo pages. Light and dark theme, Russian and English. Works offline; the previews open through a local server (a plain `file://` shows a hint to open the `http://` address instead).

<p align="center">
  <img src="assets/example-editorial.png" width="380" alt="Example: editorial style">
  <img src="assets/example-swiss-minimal.png" width="380" alt="Example: Swiss minimalism">
  <img src="assets/example-dark-luxe.png" width="380" alt="Example: dark luxe">
  <img src="assets/example-playful-morph.png" width="380" alt="Example: playful bright with morphing">
</p>

<p align="center"><sub>Four of the seven demo pages that ship with the skill. They are made by the skill itself and pass its own checker.</sub></p>

---

## Two ways in

- **A new site.** An empty folder, or a folder with only your notes. The agent starts from references and the interview.
- **An existing site.** The agent reads it first and by default redoes the design **inside the brand's identity**: colours, type and logo stay recognisable, nothing breaks. A completely new look only on your direct request.

Either way the run ends the same: `DESIGN.md` with the rules, and a block between `<!-- aidesign:start -->` and `<!-- aidesign:end -->` in the project memory file (`AGENTS.md` or `CLAUDE.md`). In an empty folder the skill creates `AGENTS.md` containing only that block.

---

## Backups and undo

Before the first edit of your files the skill makes a full copy of the project, and one more at the end of the run. The copies are folders in `.aidesign-work/backups/` (you can see them in Finder or Explorer) with a list of files and checksums; each is verified by reading it back. Under git there is also a branch or a commit, your choice.

Say «put it back as it was» — the agent shows the list of copies and restores any of them: it first saves the current state, and files that were not in the copy are not deleted but moved to a separate folder. The undo itself is `python3 .aidesign-work/backup.py restore --root . --id <copy> --yes`. Copies are never deleted without your word; a copy over 500 MB first asks you, naming the size.

---

## Design system

The project's style lives in one folder, `design-system/`: `tokens.css` — colours, fonts, spacing, radii, shadows and motion as CSS variables (the source), `tokens.json` — the same for other programs and Figma (derived from `tokens.css`), `styleguide.html` — a showcase of buttons, cards, forms and sections in your style, `README.md` — how to plug it in, `CHANGELOG.md` — what changed and why. The site takes its style only from there, and a check catches «a colour that bypasses the tokens». On an existing site the skill first writes what is already there into `design-system/` «as it was», and only then changes it. Say «pack the design system» — you get an archive you can give to a person or another agent.

---

## Figma if you want it

Figma is optional. If the site has 4 pages or more, the skill offers in one line at the end to show it in Figma; say no and it won't ask again. The connection is the official Figma MCP (`https://mcp.figma.com/mcp`); you sign in yourself in the browser:

- Claude Code — `claude mcp add --transport http figma https://mcp.figma.com/mcp` (or the plugin `figma@claude-plugins-official`);
- Codex — `codex mcp add figma --url https://mcp.figma.com/mcp`, then `codex mcp login figma`.

With a free account all pages land as frames side by side — desktop (1280) and phone (390). With a paid Figma plan and the right to edit the file the skill lays out the file itself: a cover, a page per section, a site map with arrows between pages, the design system from `tokens.json`. The code stays the source of truth: Figma holds pictures of the pages, without animation or effects. The free Figma plan allows very little reading, so the skill only puts pages there and edits the site through the code.

---

## Together with AISpa

[AISpa](https://github.com/alexfisenkov/aispa) is the sister skill that builds whole projects from a description. They work separately; together there are two orders:

- **Design first, then build.** Run `/aidesign`, choose the look, then `/aispa`. AISpa already reads `AGENTS.md`, `CONTEXT.md` and `docs/adr/`, so the build continues in the same style with nothing to adjust.
- **Build first, then polish.** Run `/aispa`. From version 1.0.3 AISpa, when its build produced a visible page and the project has no `DESIGN.md` from AI Design (the `aidesign:` key in its front matter), ends the report with one line: run `/aidesign`. It only says so; it never starts AI Design itself.

One thing to know: AISpa treats an existing `AGENTS.md` as the user's file — it does not write into it and offers additions at the end. So if AI Design created `AGENTS.md` in an empty folder, AISpa will offer its additions instead of writing them.

---

## What's built in

- `knowledge/` — the knowledge base the agent reads by route (an index points from your answers to the files): visual language (anti-patterns, type, colour, grid and rhythm, 17 style families, how to combine, how to settle disputes between sources, about 130 audit rules, the DESIGN.md format, extracting a style from a site) and motion and media (motion, scroll scenes, morphing, cursor, WebGL, photo, video, an existing site, previews, surfaces).
- `phases/` and `prompts/` — the rules of each stage and the briefs for the sub-agents that make previews, build and criticise.
- `knowledge/инструменты.md` and `knowledge/структура-проекта.md` — ready commands for screenshots, video, photos and Lighthouse, and the folder layout of a project; `knowledge/sources.json` — the registry of knowledge sources.
- `tools/ad.py` — run bookkeeping, the panel and its local server; `tools/check.py` — the template-design checker: `python3 .aidesign-work/check.py <site folder>`; `tools/setup.py` — what is installed on the computer and how to add what's missing; `tools/backup.py` — copies and undo; `tools/scaffold.py` — the project layout; `tools/designsystem.py` — tokens, the «bypassing the tokens» check, the design-system archive.
- `examples/` — seven demo pages.

It's all plain markdown, HTML and Python standard library: [skills/aidesign/SKILL.md](skills/aidesign/SKILL.md).

Tests: `python3 -B -m unittest discover -s tests`. CI runs only by hand (`workflow_dispatch`) on Linux, macOS and Windows.

---

## What AI Design is built from

AI Design is a gathering of what open design skills already know, checked against each other and cut into one process. Nothing here is hidden: for every source — what exactly was taken, in what form, under which license. **Idea** — we took the thought and wrote it in our own words. **Text** — a passage was translated or retold close to the original; such files carry a header «Источник … Изменено …». **Code** — nothing was copied: the panel and the checker are written from scratch. The full text with copyright lines and the license texts is in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). The same list for programs — `skills/aidesign/knowledge/sources.json`; how to add a newly found skill — [docs/пополнение.md](docs/пополнение.md).

| Source | What we took | How | License |
|---|---|---|---|
| [Impeccable](https://github.com/pbakaus/impeccable) (Paul Bakaus) | The catalogue of template-design marks, the «quality floor», rules for type, colour, layout and motion, visitor modes, the DESIGN.md format, token extraction | Text, retold and translated; no code | Apache-2.0 |
| [frontend-design](https://github.com/anthropics/skills/tree/main/skills/frontend-design) (Anthropic) | The list of AI-design clichés, «be bold in one place», the plan of 4–6 colours and 1–2 typefaces, interface text rules | Text, retold | Apache-2.0 |
| [Taste Skill](https://github.com/Leonxlnx/taste-skill) (Leonxlnx) | Which effects fit which kind of business, the marks of AI-written copy, the «never» list, a check-list, eleven hero layouts | Text, retold; photos and code not taken | MIT |
| [UI UX Pro Max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) (Next Level Builder) | Signs of 17 style families, UX and WCAG 2.2 rules, type pair characters, ten landing layouts, seven chart types | Text, retold; the premium version and whole data tables not taken | MIT |
| [web-design-guidelines](https://github.com/vercel-labs/agent-skills) (Vercel) | Only the idea of auditing against a fresh rule set and reporting `file:line` | Idea | MIT (stated in the README) |
| [Web Interface Guidelines](https://github.com/vercel-labs/web-interface-guidelines) (Vercel Labs) | The interface rule set: accessibility, focus, forms, animation, type, images, performance, touch, dark theme | Text, translated and adapted to Russian typography | MIT |
| [GSAP skills](https://github.com/greensock/gsap-skills) (GreenSock) | Rules for animation, ScrollTrigger, plugins and performance | Text, retold | MIT |
| [GSAP library](https://gsap.com/licensing/) | Nothing; pages that need it load it from a CDN | None | Proprietary, free to use |
| [MengTo Skills](https://github.com/MengTo/Skills) (Meng To) | Three drawing modes for scroll stories, «never hijack the wheel», scene layout, cursor-effect rules | Text, retold | MIT |
| [shaders](https://shaders.com/license) | Nothing from presets; the cursor-trail idea is described in our own words | Idea | Package MIT; presets proprietary |
| [premium-frontend-ui](https://github.com/github/awesome-copilot/tree/main/skills/premium-frontend-ui) (GitHub, author Utkarsh Patrikar) | Directions, preloader, hiding menu, magnetic buttons, custom cursor, parallax as positions in disputes; turning cursor effects off on touch | Text, retold | MIT |
| [HyperFrames](https://github.com/heygen-com/hyperframes) (HeyGen) | Ideas for media handling and video from HTML | Idea; the block catalogue not taken | Apache-2.0 |
| [hoodini/ai-agents-skills](https://github.com/hoodini/ai-agents-skills) | Ideas only: frame budget for scroll video, text scenes | Idea; no text copied (no license file) | MIT stated in the README |
| [awesome-design-md](https://github.com/VoltAgent/awesome-design-md) (VoltAgent) | The nine-section structure of DESIGN.md | Text, retold; brand files not taken | MIT |
| [getdesign.md](https://getdesign.md/terms) | Nothing; the `npx getdesign` command is named as a path you take yourself | None | Site terms |
| [Dembrandt](https://github.com/dembrandt/dembrandt) | The description of commands for extracting tokens from a site | Text, retold; no code | MIT |
| [Dembrandt skills](https://github.com/dembrandt/dembrandt-skills) | Modular type scale, algorithmic palette, extracting and reproducing a site | Text, retold | MIT |
| [scroll-world](https://github.com/oso95/scroll-world) | Ideas: art-direction interview, cost estimate before generation, seamless scene joins, a separate vertical chain for phones | Idea | MIT |

The process itself — the interview with ⚑ and «ок», the panel, run bookkeeping — comes from our own [AISpa](https://github.com/alexfisenkov/aispa). Names of companies and brands in the knowledge files are used only to name a style or a source; AI Design is not affiliated with them.

---

## License

[MIT](LICENSE) © Alexander Fisenkov, © Nick Vels (Autopilot 2.2.0, the base) — you may use, modify and distribute it, including in commercial projects.
