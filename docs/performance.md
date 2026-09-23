# Translation performance

This page gives the time and the memory that a translation needs, against the size of the
model. It answers one question: what machine do you need to translate your own model?

Every figure on this page comes from a run that we did on 2026-09-23, at interop version
0.1.0. We did not measure a solve. A solve costs far more than a translation, and the
case study pages cover it.

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
| A PLEXOS model with 86.6 MiB of traces (SEM) | 10 s | 0.96 GiB |
| A PLEXOS model with a 4.08 GiB trace directory (CAISO) | 77 s | 1.62 GiB |
| A PLEXOS model whose traces hold 199 million values (AEMO) | The run fails | More than 16 GiB |
| A PyPSA network of 26 million time series values | 13 s | 2.31 GiB |

The count of time series values sets the cost. The count of components does not, and the
length of the window that you ask for does not.

## PyPSA to Sienna

We built synthetic PyPSA networks to separate the two things that can make a model large.
Series A holds the topology at 300 components and grows the snapshots. Series B holds the
snapshots at 8,760 and grows the topology.

| Run | Components | Snapshots | Translated values | netCDF size | Time | Peak memory |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A1 | 300 | 1,000 | 250,000 | 1.98 MiB | 1.88 s | 0.30 GiB |
| A2 | 300 | 8,760 | 2,190,000 | 16.40 MiB | 2.84 s | 0.58 GiB |
| A3 | 300 | 35,040 | 8,760,000 | 65.26 MiB | 5.22 s | 1.06 GiB |
| A4 | 300 | 105,120 | 26,280,000 | 195.66 MiB | 12.92 s | 2.31 GiB |
| B2 | 3,000 | 8,760 | 21,900,000 | 162.17 MiB | 12.26 s | 2.22 GiB |
| B3 | 15,000 | 8,760 | 109,500,000 | 804.69 MiB | 67.04 s | 9.84 GiB |

"Translated values" is the snapshot count multiplied by the count of time series that the
run wrote. B1 and A2 are the same network, so the table gives that row one time.

Three facts come out of this table.

- **The topology costs almost nothing.** A4 and B2 hold about the same count of values,
  26.3 million against 21.9 million. B2 holds ten times the components of A4, 3,000
  against 300. Their time is 12.92 s against 12.26 s, and their peak memory is 2.31 GiB
  against 2.22 GiB. Ten times the topology changes neither figure.
- **The peak memory follows the count of values.** Between A2 and A4 the peak memory grows
  by about 77 bytes for each new value.
- **The time grows more slowly than the data.** A1 to A4 multiplies the values by 105 and
  the time by 6.9.

## The three PLEXOS models

These are published models. The case study pages say where to download each one.

| Model | Pipeline | XML size | Traces on disk | Snapshots | Time | Peak memory |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| [SEM 2024-2032](case_studies/sem-2024-2032.md), year 2026 | `plexos-to-pypsa` | 28.5 MiB | 86.6 MiB | 8,760 | 9.47 s | 0.93 GiB |
| SEM 2024-2032, year 2026 | `plexos-to-sienna` | 28.5 MiB | 86.6 MiB | 8,760 | 10.47 s | 0.96 GiB |
| [CAISO SA26](case_studies/caiso-sa26.md), Model `M09Y2026 SA26` | `plexos-to-pypsa` | 13.2 MiB | 4.08 GiB | 720 | 76.59 s | 1.57 GiB |
| CAISO SA26, Model `M09Y2026 SA26` | `plexos-to-sienna` | 13.2 MiB | 4.08 GiB | 720 | 73.00 s | 1.62 GiB |
| [AEMO 2024 ISP](case_studies/aemo-isp-2024.md), Step Change | `plexos-to-pypsa` | 29.1 MiB | 1.75 GiB | 17,520 | 94 s | 15.24 GiB, then the run fails |
| AEMO 2024 ISP, Step Change | `plexos-to-sienna` | 29.1 MiB | 1.75 GiB | 8,688 | 97 s | 15.25 GiB, then the run fails |

What each run wrote:

| Model | Pipeline | Components | Time series | Output size |
| --- | --- | ---: | ---: | ---: |
| SEM 2024-2032 | `plexos-to-pypsa` | 125 | 162 | 11.5 MiB |
| SEM 2024-2032 | `plexos-to-sienna` | 115 | 42 | 3.9 MiB |
| CAISO SA26 | `plexos-to-pypsa` | 676 | 850 | 4.89 MiB |
| CAISO SA26 | `plexos-to-sienna` | 691 | 394 | 4.19 MiB |
| AEMO 2024 ISP | either | none | none | none |

"Output size" counts the product files. It does not count `decisions.md`. That file is:

- 428 KB for the SEM PyPSA run
- 906 KB for the SEM Sienna run
- 2.13 MiB for the CAISO PyPSA run
- 4.98 MiB for the CAISO Sienna run

The CAISO model shows that the snapshot count does not set the cost. That run covers 720
snapshots, which is one month, and the SEM run covers 8,760 snapshots, which is a year.
The CAISO run still takes eight times as long. The CAISO trace directory holds 4.08 GiB
and the SEM trace directory holds 86.6 MiB.

The two Sienna rows cost about the same as the two PyPSA rows. `plexos-to-sienna`
composes `plexos-to-pypsa` as its first leg. That second leg adds about 1 second to the
SEM model. It adds nothing that we can measure to the CAISO model.

## The limit we reached

The AEMO Step Change model does not translate on a machine with 16 GiB of memory. The
Linux out-of-memory killer stopped all six runs with the signal `SIGKILL`, which gives the
exit status 137. Neither pipeline wrote a file.

Each run reached a peak of 15.25 GiB after about 95 seconds. Both pipelines stop in the
source, before the first translation step runs. `plexos-to-sienna` composes
`plexos-to-pypsa` as its first leg, so both stop in the same call.

**The window that you ask for does not change this.** The PyPSA run covered 17,520
snapshots and the Sienna run covered 8,688 snapshots. Their peak memory is the same to
within 0.1%.

`interop/plugins/sources/plexos_horizon.py` says why. The function
`_reconcile_to_horizon` sorts the whole series, then joins it onto the window with
`join_asof`. A sort reads every row before it writes the first one. So the volume in the
trace files sets the peak memory, and the length of the window does not.

The trace files of this model hold 199,141,392 half-hourly values, because each file
carries the whole 28 year horizon of the plan. The source reads all of them to give the
network 7,060,560 of them.

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
- **The three PLEXOS models differ in more than one way**, so the comparison between them
  shows a trend and not a controlled result. The synthetic runs above are the controlled
  result.
- **The synthetic networks left out every line.** Each synthetic line states `s_max_pu` as
  a time series, which the translator does not carry, so the run left each one out. The
  synthetic figures therefore cover buses, loads and thermal generators.
- **A translation uses about one processor.** Each CAISO run took 105% of one processor,
  so the other 7 gave it almost nothing.

## Repeat these figures

Each case study page gives the download and every prompt answer for its model. Run
`interop headless_cli` under `/usr/bin/time -v`, as [How we measured](#how-we-measured)
shows. The synthetic networks are not in this repository, because interop redistributes no
data. Build them with `pypsa` at the sizes that the Series A and Series B tables give.
