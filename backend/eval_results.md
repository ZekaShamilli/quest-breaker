# Quest-Breaker evaluation

16 held-out generated quest graphs (seeds 16-31; seeds 0-15 were used to tune the prompt), 32 planted bugs (half encoded as state flags, half only in the story text), plus 32 look-alike traps that are *not* bugs. Model: `gpt-5.6-sol`.

| Approach | Precision | Recall | Flag-bug recall | Text-only-bug recall | LLM calls | Tokens in / out | Cost | Time |
|---|---|---|---|---|---|---|---|---|
| Graph-only (NetworkX) | 100% | 50% | 100% | 0% | 0 | 0 / 0 | $0.00 | 0.0s |
| LLM-only (whole graph, 1 call) | 100% | 62% | 25% | 100% | 16 | 25,569 / 5,734 | n/a (set QB_PRICE_IN/OUT) | 8.6s |
| **Hybrid (Quest-Breaker)** | 100% | 100% | 100% | 100% | 48 | 37,752 / 3,052 | n/a (set QB_PRICE_IN/OUT) | 6.5s |

## Failures: Graph-only (NetworkX)

- **missed** `bench_16` text_bug aydan: caused at `a1`, shows up at `hub2`
- **missed** `bench_17` text_bug mirza: caused at `a4`, shows up at `hub6`
- **missed** `bench_18` text_bug garrick: caused at `a1`, shows up at `hub5`
- **missed** `bench_19` text_bug gull: caused at `a0`, shows up at `hub3`
- **missed** `bench_20` text_bug mirza: caused at `a0`, shows up at `hub2`
- **missed** `bench_21` text_bug aydan: caused at `a1`, shows up at `hub5`
- **missed** `bench_22` text_bug ysolde: caused at `a0`, shows up at `hub6`
- **missed** `bench_23` text_bug gull: caused at `a3`, shows up at `hub5`
- **missed** `bench_24` text_bug mirza: caused at `a0`, shows up at `hub6`
- **missed** `bench_25` text_bug mirza: caused at `a0`, shows up at `hub3`

## Failures: LLM-only (whole graph, 1 call)

- **missed** `bench_17` flag_bug gull: caused at `a2`, shows up at `hub4`
- **missed** `bench_18` flag_bug bridge: caused at `a2`, shows up at `hub4`
- **missed** `bench_19` flag_bug garrick: caused at `a4`, shows up at `hub5`
- **missed** `bench_20` flag_bug bridge: caused at `a2`, shows up at `hub4`
- **missed** `bench_23` flag_bug oracle: caused at `a4`, shows up at `hub6`
- **missed** `bench_24` flag_bug gull: caused at `a1`, shows up at `hub3`
- **missed** `bench_25` flag_bug gull: caused at `a2`, shows up at `hub6`
- **missed** `bench_26` flag_bug aydan: caused at `a4`, shows up at `hub5`
- **missed** `bench_27` flag_bug mirza: caused at `a1`, shows up at `hub2`
- **missed** `bench_28` flag_bug ysolde: caused at `a4`, shows up at `hub5`
