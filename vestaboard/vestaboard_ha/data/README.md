# holidays.json

A day-by-day list of the small invented holidays -- National Donut Day, Talk
Like a Pirate Day -- so the board can say what today is.

## Where it came from

Vendored verbatim from [mezotv/TodayIsThatDay][repo], file
`src/data/holidays.json`, which is [MIT licensed][license]. A copy of that
license sits next to this file as `holidays.json.LICENSE`.

[repo]: https://github.com/mezotv/TodayIsThatDay
[license]: https://github.com/mezotv/TodayIsThatDay/blob/main/LICENSE

## Shape

Month name, then day-of-month as a string, then the names for that day:

```json
{ "September": { "19": ["National Butterscotch Pudding Day",
                        "Talk Like a Pirate Day"] } }
```

1429 names over 366 days. Every day of the year has at least one, February 29
included, and every one has a fixed date -- nothing in here floats, which is
why this file and not a rules engine.

## What it takes to put one on the board

The board is a Note: three rows of fifteen, so 45 chips with the word breaks
falling where they may. That is the real constraint, and this list clears it:

- Every character used is one the board has. No accents, no em dashes, nothing
  that has to be transliterated before it can be encoded.
- 1379 of the 1429 names wrap into three rows as they are written. The other 50
  are long ones like `National Sneak Some Zucchini Into Your Neighbors Porch
  Day`.
- All 366 days have at least one name that fits, so no day has to fall back to
  something else.

Dropping a leading `National` / `World` / `International` buys nine to fourteen
chips and takes the fit to 1420 of 1429, which also reads better -- `BLOODY
MARY DAY` on one row beats `NATIONAL BLOODY` / `MARY DAY` broken across two.

A few names carry a trailing space (`"National Just One Human Family "`), so
strip and collapse whitespace on the way in rather than trusting the file.

## Updating

Nothing here is generated, so refreshing it means fetching the file again:

```
curl -sSL -o vestaboard/vestaboard_ha/data/holidays.json \
  https://raw.githubusercontent.com/mezotv/TodayIsThatDay/main/src/data/holidays.json
```

Upstream is a small Twitter bot and moves rarely, so expect that to be a no-op
most of the time.
