# Design cleanup plan

> **Status: done, 11 Sep 2026.** Every screen below is shipped and live. Covered
> by 60 tests plus a scripted browser run of the pick flow. `make shots`
> captures all screens at phone/desktop in light/dark for review.


Goal: clean, modern, quiet. The site should look like a well-made sports app
used by five friends, not a product page describing itself.

## What's wrong now

| Problem | Where it comes from |
|---|---|
| **Cartoony** | Emoji in the header and favicon; extra-bold (800) headings; bordered, tinted "chips" for WIN / LOSS / LOCKED / OWNER; green on every button, pill, tab and progress bar |
| **Techy / over-styled** | Monospace, uppercase, letter-spaced labels everywhere ("WEEK 1 BOARD", "LEADERBOARD · ALL TIME", "MARGIN") |
| **Heavy** | Every section is a bordered card with a grey header band; the stats page stacks nine of them |
| **Reads like an ad** | The landing page describes features; helper sentences explain how the app works on nearly every screen; credits like "via ESPN" and "pre-filled from DraftKings" |

## Direction

**Monochrome interface, colour only for results.** Chrome is black, white and
greys. Green and red appear only where they mean win and loss. Hierarchy comes
from size, weight and spacing instead of boxes and colour. The closest
reference is the Apple Sports app: dense, calm, all about the numbers.

### Rules for copy

1. No sentence on the site explains a feature or how the app works.
2. Labels are short nouns in sentence case: "Standings", not "LEADERBOARD · ALL TIME".
3. Show state as data, not prose: "3 of 5", plus the names still to pick,
   instead of "Waiting on 2 more. The text goes out when everyone's in."
4. Only two kinds of sentence are allowed: errors ("Enter a number like -3.5")
   and confirmations ("Link sent to pat@…").
5. No credits or attributions in the UI.

## Tokens

**Type.** Geist Sans at 400/500/600, with no 700 or 800. It's crisp, neutral
and has good tabular figures. Self-host the woff2 files, which also removes the
Google Fonts request. Scale: 12 / 14 / 16 / 20 / 28. Tabular numbers on every
record, line and unit figure. Drop the monospace face entirely.

**Colour.**

| Token | Light | Dark |
|---|---|---|
| background | `#FFFFFF` | `#0A0A0A` |
| surface (inputs, hover) | `#F5F5F5` | `#171717` |
| text | `#0A0A0A` | `#EDEDED` |
| secondary text | `#737373` | `#A1A1A1` |
| hairline | `#E5E5E5` | `#262626` |
| win | `#15803D` | `#4ADE80` |
| loss | `#B91C1C` | `#F87171` |
| push | `#737373` | `#A1A1A1` |

Primary buttons use the text colour (black in light mode, white in dark). The
five player colours stay only in the chart, where they're already validated for
colour blindness.

**Shape.** 8px radius on inputs and buttons. No card borders around page
sections, no shadows. 1px hairlines only between table rows and around inputs.
Spacing on a 4px grid, and generous: sections separated by 40px of space rather
than boxes.

**Theme.** Follow the system light/dark setting and remove the sun toggle. It
saves one control in the header.

## Components

These replace the current `.card`, `.label` and `.chip` classes.

- **Result mark.** A plain coloured letter, **W** / **L** / **P**, in semibold.
  No border and no background.
- **Row.** Name on the left, detail below it in secondary text, value on the
  right. Hairline divider. Used for picks, members and games.
- **Segmented control.** A grey track with a white selected segment, for bet
  type, team and season.
- **Table.** Plain header in secondary text, hairline rows, numbers
  right-aligned.
- **Buttons.** Primary (filled) and plain (text only). One primary per screen.

## Screens

### Shell
- Header: the wordmark "Parlay" in 600 weight on the left, nav on the right
  (Board · Stats · Settings), with the active item shown as a text colour
  change rather than a green pill. No emoji. No syndicate name, since there's
  only one.
- Mobile: a bottom tab bar with simple line icons and labels.
- Remove the footer.
- Favicon: a black rounded square with a white "P".
- **Bug fix:** clicking your name in the header currently signs you out. Move
  sign out to Settings.

### Landing, sign-in, invite
The root page becomes the sign-in page: wordmark, email field, "Continue",
and a small "Start a new syndicate" link. No tagline, no feature tiles.

```
            Parlay

   ┌──────────────────────────┐
   │ Email                    │
   └──────────────────────────┘
   [        Continue          ]

        Start a new syndicate
```

- Link sent: "Check your email" plus the address. Nothing else.
- Invite: "Join Shed Parlay" and a button. Nothing else.

### Board (the main screen)
This week's picks come first; your own pick is a single row once it's made.

```
 ‹  Week 1  ›                    3 of 5
    Sep 10 – 14

 Your pick
 Over 44.5 · NE @ SEA           Edit

 Picks
 Pat      Over 44.5             NE @ SEA · Thu
 Leland   Lions −7              NO @ DET · Sun
 Hank     Bills −1.5            BUF @ HOU · Sun
 Ben      —
 BD       —

 Season
 Pat 10–7   Leland 9–8   Ben 8–9   Hank 6–11   BD 6–11
```

- Before you've picked, the "Your pick" area is the form. After you pick, it
  collapses to the one row above, with Edit to reopen it.
- Members who haven't picked appear as muted rows with a dash. That replaces
  both "No picks in yet" and "Waiting on N more…".
- Once graded, each row gets a **W** / **L** / **P** mark and the final score.
- Remove the separate "Games & lines" panel, since the game picker already
  shows every line.
- **Pick form.** Keep it compact: game, bet type (segmented), team if it's a
  spread (segmented), line. Remove "pre-filled from DraftKings" and the
  half-point helper text. The line still pre-fills, and errors say what's wrong.
- *Larger optional change:* replace the game dropdown with a tappable list of
  games (matchup, spread, total, kickoff), Apple Sports style. It's better on a
  phone but more work. Worth doing after the rest lands.

### Stats
- A season segmented control at the top: All time · 2025 · 2024 · 2023.
- Sections with plain headings and no boxes, in this order: Standings, Units
  (chart), Streaks, By bet type, Favourites vs underdogs, Weekly wins, Teams,
  Close losses.
- Remove every explainer. Where a section needed one, the column headers carry
  it: Weekly wins becomes the columns "Only winner" and "Shared", with no
  paragraph.
- Remove "1 unit risked per pick at −110" and the "Never picked…" line.
- Headline numbers become one quiet row (Record · Units · Picks) instead of
  four bordered tiles.

### Settings
A grouped list, like iOS Settings:

- **Members:** one row per person. The owner sees an Edit action to set email
  and phone. Placeholder addresses show as an empty field, with no warning
  sentence.
- **Invite:** email field and Send. The link appears below it after sending,
  with a Copy button.
- **Syndicate:** name, juice, and the lock-at-kickoff switch. No helper text.
- **Account:** display name, phone, Sign out.
- Remove the "Texting is off — set SMS_ENABLED…" line. Server configuration
  doesn't belong in the UI.

## Order of work

1. **Foundation.** Tokens, self-hosted Geist, the new components; delete
   `.card` / `.label` / `.chip`.
2. **Shell.** Header, tab bar, favicon, footer removal, theme, sign-out fix.
3. **Sign-in, invite and message pages.**
4. **Board**, including pending-member rows and the collapsed "your pick" row.
5. **Stats.**
6. **Settings.**
7. **Tests.** Several tests assert on copy that's being deleted ("Everyone
   picks one game", "Make your pick", "LOCKED", "pre-filled"). Update them to
   assert on behaviour instead.
8. **Visual QA.** Screenshots of every screen at phone (390px) and desktop
   (1280px) widths, in light and dark mode, reviewed before each deploy.

Each step ships on its own: tests pass, deploy with
`sudo systemctl restart parlay`, and check it on the live site.

## Testing the look

Proper design QA needs screenshots, and the VM has no browser. Headless
Chromium via Playwright needs about 400 MB, and the disk has 779 MB free, so
space needs clearing first. Nothing below touches haneytube or the other
sites:

| Reclaim | Size |
|---|---|
| `parlay/venv/`, the dead 2023 Python 3.9 virtualenv | 210 MB |
| Old system journal logs (`journalctl --vacuum-size=200M`) | ~1.2 GB |
| apt package cache (`apt-get clean`) | 107 MB |

With that done, `scripts/screenshots.py` can capture every screen in both
themes at both widths for review.

## Decisions I've made that you may want to override

- **Geist** rather than the phone's native system font. Geist looks the same on
  every device; the system font would feel more native but vary by phone.
- **No theme toggle.** The site follows the phone's own light/dark setting.
- **No syndicate name in the header.** It comes back automatically if you ever
  join a second syndicate.
- **Season standings stay on the board** as one compact line, because checking
  records is the fun part. They could move to Stats only.
