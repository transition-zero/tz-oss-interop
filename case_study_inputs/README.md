# Case study inputs

Put the published models in this directory. Git ignores all the files in this directory
except this file.

Each case study page tells you which file to download. This table tells you where to put
it.

| Put it in | Case study |
| --- | --- |
| `caiso-sa26/` | [CAISO 2026 Summer Assessment](../docs/case_studies/caiso-sa26.md) |
| `sem-2024-2032/` | [SEM 2024-2032 Validation](../docs/case_studies/sem-2024-2032.md) |
| `aemo-isp-2024/` | [AEMO 2024 ISP](../docs/case_studies/aemo-isp-2024.md) |

A case study can also ask for reference data: the numbers the publisher states in its
report, which you write out as CSV files and put beside the model. The case study page
gives every column such a file needs.

Each model has time series traces. The publisher supplies these traces in files that are
separate from the XML file.

Do not change the directory layout of the publisher. The XML file gives a relative path
for each trace file. The translator finds each trace file from the location of the XML
file.
