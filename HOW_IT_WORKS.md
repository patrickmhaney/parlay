# How Parlay works

The whole flow, from sign-in to the Tuesday text. All times are Eastern.

---

## 1. Signing in

There are no passwords.

1. You enter your email at parlaysyndicate.com and tap **Continue**.
2. The site emails you a sign-in link (sent by Resend, from
   noreply@parlaysyndicate.com). The link works **once**, for **15 minutes**.
3. Tapping it signs you in on that device for **120 days**.

- **Limit:** one address can be sent at most 3 links per 15 minutes, so the
  site can't be used to flood someone's inbox.
- **Which account:** the email address *is* the account. Each of the five of
  you has an address on your existing account, which holds your history.
  Signing in with a different address creates a new, empty account; it lands
  on a "New syndicate" page, where you can sign out and try the right address.
- **Signing out:** Settings → Sign out.

## 2. Syndicates and invites

A syndicate is a group that plays together: yours is Shed Parlay, with five
members, and you're the owner.

- **The owner** can edit members' email and phone, send invites, rename the
  syndicate, and turn "lock picks at kickoff" on or off.
- **Invites** (Settings → Invite) email a join link that lasts 14 days. You
  can also copy the link and text it. Whoever opens it signs in, taps
  **Join**, and is a member.
- **Starting a new syndicate:** anyone can, from the sign-in page ("Start a new
  syndicate"). That's how you'd hand the site to another group.

## 3. Where the games and lines come from

Everything comes from **ESPN's public scoreboard feed**:

- the schedule (every game, kickoff times),
- the **betting lines**: ESPN publishes **DraftKings'** current spread and
  over/under for games that haven't started,
- live and final **scores**.

**When it refreshes:** every hour, at 17 minutes past, for every week of the
current season that still has an unfinished game. So a line on the site is
at most about an hour old, and it's DraftKings' *current* number at that time,
not the opening line.

Once a game is final, ESPN stops publishing its line; the site keeps the last
one it saw. Past weeks, whose games are all final, are saved and never
re-fetched.

## 4. Making a pick

On the Board, **Your pick** has four fields:

| Field | What it does |
|---|---|
| Game | This week's games, with the current spread and total next to each |
| Bet | Spread, Over, or Under |
| Team | Spread only: which side you're taking |
| Line | Pre-filled with DraftKings' number for what you chose. Change it to match the number your own book gave you |

- **The line you enter is the line you're graded on.** That's why it's
  editable: everyone bets at their own book.
- **Checks:** the line must be a number in half points (−3.5, 44, +7) in a
  sensible range, and a spread must be for one of the two teams in that game.
- **One pick per person per week.** Saving again replaces your pick. After you
  submit, it collapses to one line with **Edit**.
- **Kickoff lock** (on by default): you can't pick a game that has already
  started, and once your own game kicks off your pick is final.
- **Board lock:** when the last member picks, the whole week locks. Nobody can
  change their pick after that, even if their game hasn't started.

Everyone sees picks as soon as they're made. Members who haven't picked show
as a dash.

## 5. The "picks are in" text

**Trigger:** the moment the number of picks for a week equals the number of
members (5 of 5). The same submit that completes the board locks it and sends
the text, to every member with a phone number:

```
The picks are in!
-BD: Giants +7.5
-Ben: Under 35.5 49ers/Browns
...
https://parlaysyndicate.com
```

It's sent **exactly once per week**, even if something retries. If someone
never picks, the board never locks and this text doesn't go out.

Texts are sent through Textbelt, using your key.

## 6. Grading: who won each bet

"Grading" is settling a bet once the game is final. Only the final score is
needed, because each person's line is already recorded with their pick.

| Bet | Wins when | Loses when | Push |
|---|---|---|---|
| Spread | your team's score **+ your line** beats theirs | it's below theirs | exactly equal |
| Over | combined score is **above** your number | below | exactly equal |
| Under | combined score is **below** your number | above | exactly equal |

Example: Titans +2.5 lose 20–22. 20 + 2.5 = 22.5, which beats 22, so that's
a **win** by 0.5.

**When:** every hour, straight after the score refresh. Any pick whose game
has gone final gets a **W**, **L** or **P** within about an hour of the final
whistle, Thursday nights included.

## 7. The parlay and the goose

Each week's picks are the legs of one shared parlay. The site uses standard
sportsbook rules:

- **Hit:** no leg lost. A pushed leg drops out and the rest still count, so
  4 wins and a push is a hit.
- **Missed:** any leg lost. It shows as missed the moment the first leg loses,
  even with games still to play.
- **Alive:** nothing has lost yet and games are still to be played.
- **The goose:** the one person whose leg lost when every other leg won (or
  pushed). The only thing between the group and a hit.

This shows at the top of the Board for each week.

## 8. The results text (only when you win)

**Trigger:** every morning at **7:00** (6:00 once clocks go back in
November), the site does a final score refresh and grading pass, then looks
for a week where **every pick is graded**. In practice that's Tuesday
morning, after Monday night's game.

- **If the parlay hit**, everyone gets:
  ```
  Week 3: THE PARLAY HIT!
  -BD: W  Under 38.5 Giants/Browns
  ...
  ```
- **If it missed, no text.** Nobody needs reminding. The week is marked done
  either way, so it's never reconsidered, and it's on the Board and in Stats
  as usual.

Every past season's week is already marked done, so old results never go out.

## 9. Stats

All computed live from graded picks. Filter by season or all time.

- **Parlays hit**: how many weeks hit, and which.
- **Standings**: each person's record, win %, and geese.
- **Wins minus losses**: a line per person across the season.
- **Streaks**: current, best and worst.
- **By bet type** and **favorites vs underdogs**.
- **Most-picked teams** and **close losses** (lost by a point or less).

## 10. The schedule at a glance

| When (Eastern) | What happens |
|---|---|
| Any time | Picks shown as they're made; the board locks and texts on the last pick |
| Every hour at :17 | Lines and scores refresh; finished games are graded |
| 7:00 AM daily | Final refresh and grading; a text if a finished week's parlay hit |
| Midnight | Expired sign-in links and sessions are cleaned up |

## 11. Not automated yet, and things to know

- **No automatic backups are running.** The nightly backup in the Docker setup
  isn't used on this VM. `make backup` takes one by hand, and there are
  manual backups from each change in `backups/`. This should get a nightly
  timer.
- **No screen for correcting a result.** The site can store a manual
  correction, but there's no button for it yet. Grading has been right on all
  265 historical picks, but if ESPN ever posts a wrong score, a fix currently
  means asking me.
- **Textbelt credits:** 168 left. Each week sends 5 "picks are in" texts (plus 5 more
  in the rare week the parlay hits), and longer texts can count as two credits, so expect to
  top up partway through the season.
- **Game lines are a starting point.** They're DraftKings' number as of the
  last hourly refresh; enter your own book's number if it differs.
