# AI service — metrics & Grafana

The `ai` service exposes Prometheus metrics on port `8000` (mapped to
`:8050` when running via `ai/scripts/dev-run.sh`). This doc covers the
custom metrics defined in `ai/variables.py` and how to graph them correctly
in Grafana — the two metric types (`Gauge` vs `Histogram`) need different
query patterns, and getting a `Histogram` wrong is an easy mistake to make.

Quick local check without Grafana: `ai/scripts/dev-run.sh metrics` dumps
these same metrics filtered of the standard `python_*`/`process_*`
boilerplate `prometheus_client` adds automatically.

## The metrics

| Metric | Type | Labels | What it means |
|---|---|---|---|
| `thread_count_total` | Gauge | - | Number of currently-running Creature threads |
| `thread_count_fungus` | Gauge | - | Of those, how many are `Fungus` |
| `thread_count_salamander` | Gauge | - | Of those, how many are `Salamander` |
| `creature_tick_seconds` | Histogram | `species` | Time spent processing one Creature's tick (`get_pa`/`get_creature`/`status`/`move`), excluding the deliberate `sleep()` |
| `creature_thread_died_unexpectedly_total` | Counter | `species` | A Creature's thread was found dead by the reconciler without having gone through `creature_kill()` - i.e. it crashed |

`creature_tick_seconds` is aggregated **per species, not per creature** — a
single Salamander vs a hundred Salamanders show up in the same time series,
just with a higher `_count`. This was a deliberate choice to keep the metric's
cardinality bounded as the creature count grows (see the scaling discussion
in `ARCHITECTURE.md`) — if you ever need to debug one specific misbehaving
creature, that's a job for the logs (`{self.logh}` prefixes every log line
with the Creature's id/name), not this metric.

## Adding the data source

Standard Prometheus setup, nothing `ai`-specific: in Grafana, add a
Prometheus data source pointing at wherever your Prometheus server scrapes
this service's `:8000/metrics` (or `:8050` if you're pointing Grafana at a
`dev-run.sh` instance directly for a quick local look — there's no scrape
config in this repo for that, it's meant for manual `curl`/browser checks,
so add it as a one-off data source URL if you want it in Grafana too).

## Graphing the Gauges (`thread_count_*`)

These are straightforward — a `Gauge` is just "the current value," so query
them directly:

```promql
thread_count_total
thread_count_fungus
thread_count_salamander
```

Good panel types: **Stat** (current count) or **Time series** (count over
time, to see spawn/despawn activity). No `rate()` or aggregation needed.

## Graphing the Histogram (`creature_tick_seconds`) - read this part carefully

`_count` and `_sum` (and the `_bucket{le="..."}` series) are **cumulative
counters** - they only ever go up, and they reset to 0 when the process
restarts. Graphing them raw (e.g. just `creature_tick_seconds_sum`) produces
a meaningless ever-climbing line with a cliff on every deploy. You need
`rate()` or `increase()` over a time window first, same as you would for any
Prometheus counter.

**Average tick duration per species:**
```promql
rate(creature_tick_seconds_sum[5m])
  /
rate(creature_tick_seconds_count[5m])
```
Panel type: **Time series**, one line per `species` (Grafana will split by
label automatically).

**p95 / p99 tick duration per species** (the metric that actually matters
for spotting tick-overrun risk before it happens):
```promql
histogram_quantile(
  0.95,
  sum(rate(creature_tick_seconds_bucket[5m])) by (le, species)
)
```
Swap `0.95` for `0.99` for the tail. Panel type: **Time series**.

**Distribution / heatmap** (how tick durations are spread across buckets
over time - useful for spotting a shift in the whole distribution, not just
the tail):
```promql
sum(rate(creature_tick_seconds_bucket[5m])) by (le, species)
```
Panel type: **Heatmap**, with "Format" set to `Time series buckets` (Grafana
detects the `le` label and stacks it into a heatmap automatically).

## Graphing `creature_thread_died_unexpectedly_total`

Same rule as the Histogram above: this is a **Counter**, so query it with
`rate()`/`increase()`, not raw.

**Are we losing Creature threads?**
```promql
increase(creature_thread_died_unexpectedly_total[15m])
```
Panel type: **Stat** or **Time series**. In normal operation this should be
flat at 0 - any nonzero value means the reconciler (`ai/utils/actions.py`,
swept every `RECONCILE_INTERVAL` seconds, default 30s, see `variables.py`)
found a Creature thread that had died without going through `creature_kill()`.
That's always worth investigating: it means something threw an unhandled
exception inside that Creature's tick loop (`Mob.run()` in
`ai/bestiaire/_Mob.py`) badly enough to kill the whole thread. Check the logs
around the same timestamp for a `Creature thread died unexpectedly` line -
it includes the Creature's id/name so you can correlate with whatever else
that Creature was doing.

**This is the metric that would have caught the Redis connection-pool
exhaustion bug found during this service's load testing** (see
`ARCHITECTURE.md`) - before the reconciler existed, that failure mode was
completely invisible: `/threads` and `thread_count_total` kept reporting
every Creature as alive while the underlying OS threads had actually died.
A Grafana alert on `increase(creature_thread_died_unexpectedly_total[15m]) > 0`
is a reasonable default if you want to be paged on this rather than notice it
in a dashboard.

## A note on alerting for tick overrun

`ai/bestiaire/{Fungus,Salamander}.py` already logs a `Tick overrun risk`
warning (see `_Mob.py`/`TICK_OVERRUN_THRESHOLD` in `variables.py`) whenever a
single tick exceeds 80% of that Creature's Instance's tick budget. That
threshold is evaluated in Python against `self.instance.tick`, which is
per-Instance and **not currently exposed as a metric** - so there isn't a
pure-PromQL way to alert on "p95 is approaching the tick budget" today,
since Prometheus doesn't know what the budget is. Two options if you want a
Grafana/Prometheus alert rather than relying on the log line:
- Alert on the p95 query above crossing a fixed absolute threshold you pick
  based on your instances' typical tick length (simple, but not adaptive if
  different Instances use very different tick values).
- Export `instance.tick` as its own Gauge (labeled by instance) so a PromQL
  alert can compute the ratio directly - not implemented yet, flagged here
  as the natural follow-up if per-Instance tick budgets start varying enough
  to matter.
