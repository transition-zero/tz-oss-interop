# Translation performance

This page gives the time and the memory that a translation needs, against the size of the
model. It answers one question: what machine do you need to translate your own model?

Every figure on this page comes from a run that we did on 2026-09-24, at interop version
0.1.0, commit `f5fa4f2`. We did not measure a solve. A solve costs far more than a
translation, and the case study pages cover it.

## The machine

Each run used one machine of this shape:

| Item | Value |
| --- | --- |
| Processors | 8 |
| Memory | 16 GiB, with no swap |
| Disk | 64 GB |
| Python | 3.13.15 |
| Operating system | Amazon Linux 2023, x86_64 |

## How we measured

We ran each translation through the headless CLI, under `/usr/bin/time -v`:

```bash
/usr/bin/time -v uv run interop headless_cli --pipeline <name> --override '<node.field>=<value>'
```

Two lines of that output give the figures on this page. `Elapsed (wall clock) time` gives
the time column. `Maximum resident set size` gives the peak memory column.

Each run went three times, and each table gives the median of the three.

## The short answer

Each row below is a model that we ran, and not a rule that we derived.

| The model we ran | Time | Peak memory |
| --- | ---: | ---: |
| A PLEXOS model with 86.6 MiB of traces (SEM) | 12 s | 0.85 GiB |
| A PLEXOS model with a 4.08 GiB trace directory (CAISO) | 74 s | 1.62 GiB |
| A PLEXOS model whose traces hold 199 million values (AEMO) | 109 s | 2.31 GiB |
| A PyPSA network of 26 million time series values | 19 s | 0.88 GiB |
| A PyPSA network of 110 million time series values | 99 s | 3.14 GiB |

A laptop with 8 GiB of memory translates each of these models.

## PyPSA to Sienna

We built synthetic PyPSA networks to separate the two things that can make a model large.
Series A holds the topology at 300 components and grows the snapshots. Series B holds the
snapshots at 8,760 and grows the topology.

| Run | Components | Snapshots | Translated values | netCDF size | Time | Peak memory |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A1 | 300 | 1,000 | 250,000 | 1.98 MiB | 2.06 s | 0.30 GiB |
| A2 | 300 | 8,760 | 2,190,000 | 16.40 MiB | 2.93 s | 0.59 GiB |
| A3 | 300 | 35,040 | 8,760,000 | 65.26 MiB | 6.95 s | 0.75 GiB |
| A4 | 300 | 105,120 | 26,280,000 | 195.66 MiB | 18.79 s | 0.88 GiB |
| B2 | 3,000 | 8,760 | 21,900,000 | 162.17 MiB | 17.28 s | 0.90 GiB |
| B3 | 15,000 | 8,760 | 109,500,000 | 804.69 MiB | 98.99 s | 3.14 GiB |

"Translated values" is the snapshot count multiplied by the count of time series that the
run wrote. B1 and A2 are the same network, so the table gives that row one time.

Three facts come out of this table.

- **The topology costs almost nothing.** A4 and B2 hold about the same count of values,
  26.3 million against 21.9 million. B2 holds ten times the components of A4, 3,000
  against 300. Their time is 18.79 s against 17.28 s, and their peak memory is 0.88 GiB
  against 0.90 GiB. Ten times the topology changes neither figure.
- **The peak memory grows slowly.** A1 to A4 multiplies the values by 105 and the peak
  memory by 3. Between A2 and A4 the peak memory grows by about 13 bytes for each new
  value. The translator reads and writes the values in blocks, and holds one block at a
  time.
- **The time grows more slowly than the data.** A1 to A4 multiplies the values by 105 and
  the time by 9.1.

## The three PLEXOS models

These are published models. The case study pages say where to download each one.
`plexos-to-sienna` is one direct pipeline. `plexos-to-pypsa` runs `plexos-to-sienna` and
then `sienna-to-pypsa`, so each of its rows holds both legs.

| Model | Pipeline | XML size | Traces on disk | Snapshots | Time | Peak memory |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| [SEM 2024-2032](case_studies/sem-2024-2032.md), year 2026 | `plexos-to-pypsa` | 28.5 MiB | 86.6 MiB | 8,760 | 11.53 s | 0.85 GiB |
| SEM 2024-2032, year 2026 | `plexos-to-sienna` | 28.5 MiB | 86.6 MiB | 8,760 | 7.16 s | 0.63 GiB |
| [CAISO SA26](case_studies/caiso-sa26.md), Model `M09Y2026 SA26` | `plexos-to-pypsa` | 13.2 MiB | 4.08 GiB | 720 | 73.75 s | 1.62 GiB |
| CAISO SA26, Model `M09Y2026 SA26` | `plexos-to-sienna` | 13.2 MiB | 4.08 GiB | 720 | 69.79 s | 1.38 GiB |
| [AEMO 2024 ISP](case_studies/aemo-isp-2024.md), Step Change, whole Horizon | `plexos-to-pypsa` | 29.1 MiB | 1.75 GiB | 17,520 | 109.32 s | 2.31 GiB |
| AEMO 2024 ISP, Step Change, year 2025 | `plexos-to-sienna` | 29.1 MiB | 1.75 GiB | 8,688 | 105.59 s | 2.10 GiB |

What each run wrote:

| Model | Pipeline | Components | Time series | Output size |
| --- | --- | ---: | ---: | ---: |
| SEM 2024-2032 | `plexos-to-pypsa` | 110 | 102 | 7.9 MiB |
| SEM 2024-2032 | `plexos-to-sienna` | 115 | 42 | 3.9 MiB |
| CAISO SA26 | `plexos-to-pypsa` | 676 | 654 | 3.81 MiB |
| CAISO SA26 | `plexos-to-sienna` | 691 | 412 | 4.43 MiB |
| AEMO 2024 ISP | `plexos-to-pypsa` | not counted | not counted | 26.8 MiB |
| AEMO 2024 ISP | `plexos-to-sienna` | 689 | 202 | 16.0 MiB |

"Output size" counts the product files. It does not count `decisions.md`, which for the
AEMO model is:

- 4.05 MiB for the AEMO PyPSA run
- 2.56 MiB for the AEMO Sienna run

The PyPSA row of each model costs more than its Sienna row, because it runs the Sienna
leg and then the leg back to PyPSA. That second leg adds about 4 seconds to the SEM and
CAISO models, and about 4 seconds to the AEMO model.

## What sets the cost

The count of time series values that the run reads sets the time. The CAISO run covers
720 snapshots, which is one month, and the SEM run covers 8,760 snapshots, which is a
year. The CAISO run still takes eight times as long. The CAISO trace directory holds
4.08 GiB and the SEM trace directory holds 86.6 MiB.

The count of components changes neither the time nor the memory. The synthetic runs
above show that.

The window that you ask for does not change the memory of a PLEXOS run. Each trace file
of the AEMO model carries the whole 28 year horizon of the plan at half-hourly
resolution, which is 199,141,392 values in total. The two AEMO runs cover 17,520 and
8,688 snapshots, and their peak memory is the same to within 1%. The source keeps the
rows inside the window and the last row before it, and drops the rest before it sorts.
The rows it drops still cost the time to read them.

## What the figures do not cover

- **We did not measure a solve.** A solve costs far more than a translation. The case
  study pages say what each solve costs.
- **We did not measure the Monte Carlo pipelines.** The CAISO runs used the plain
  `plexos-to-pypsa` and `plexos-to-sienna` pipelines, and read one replication.
  `plexos-to-pypsa-monte-carlo` reads many, so it costs more.
- **We did not measure how many of the 4.08 GiB of CAISO traces a run reads.** A plain run
  reads the September month and one replication, so it reads a part of that directory. We
  give the directory size because you can compare it against your own model. A run does
  not read all of it.
- **We did not trace where the CAISO peak memory sits.** It is not in the time series,
  because the window narrowing changed it by less than 0.1 GiB.
- **The three PLEXOS models differ in more than one way**, so the comparison between them
  shows a trend and not a controlled result. The synthetic runs above are the controlled
  result.
- **The synthetic networks left out every line.** Each synthetic line states `s_max_pu` as
  a time series, which the translator does not carry, so the run left each one out. The
  synthetic figures therefore cover buses, loads and thermal generators.
- **A translation uses between one and two processors.** Each CAISO run took 105% of one
  processor, and each AEMO run took 172%, so the other cores gave it little.

## Repeat these figures

Each case study page gives the download and every prompt answer for its model. Run
`interop headless_cli` under `/usr/bin/time -v`, as [How we measured](#how-we-measured)
shows. The synthetic networks are not in this repository, because interop redistributes no
data. Build them with `pypsa` at the sizes that the Series A and Series B tables give.
