# AETOS

## The model

AETOS (Africa–Europe Energy Transition OSeMOSYS) is an open-source OSeMOSYS model of 78
countries: 48 in Africa and 30 in Europe. It models electricity and natural gas, and the trade
of both between the countries. Its years are 2021 to 2055.

AETOS has one OSeMOSYS region, `REGION1`. Each technology name and each fuel name starts with
the two-letter code of its country, for example `DZNGCCPH1` and `DZE1`.

The size makes this model a good test of the canonical stage. The model has 224 CSV files, 3158
technologies and 804 fuels.

## Get the input

The authors publish AETOS version `v2.0.0` in two places: the
[GitHub tag `v2.0.0`](https://github.com/ekousoulos/AETOS-model/tree/v2.0.0) and the
[Zenodo record 18479411](https://doi.org/10.5281/zenodo.18479411). The model is licensed under
the MIT licence. Cite it as the AETOS `README.md` says.

The repository holds the model inputs, so you can clone the tag:

```sh
git clone --depth 1 --branch v2.0.0 https://github.com/ekousoulos/AETOS-model.git case_study_inputs/aetos
rm -rf case_study_inputs/aetos/.git
```

You can also download the archive from Zenodo:

```sh
curl -L -o /tmp/aetos-v2.0.0.zip "https://zenodo.org/records/18479411/files/ekousoulos/AETOS-model-v2.0.0.zip?download=1"
md5sum /tmp/aetos-v2.0.0.zip
```

The checksum must be `76bcfbe64fe92f36d7dffc2993f50a9f`. Extract the archive. Then move the
top-level directory of the archive to `case_study_inputs/aetos/`.

| | |
| --- | --- |
| Download size | 98.4 MB for the Zenodo archive |
| Size on disk | 444 MB, of which the CSV files are 40 MB |
| Put it in | `case_study_inputs/aetos/` |

Do not change the directory layout of the publisher. The run reads two paths in
`case_study_inputs/aetos/AETOS_Runner/`:

- `config_otoole_AETOS.yaml` is the otoole configuration.
- `CSVFiles/` holds one CSV file for each OSeMOSYS set and parameter.

## The mappings file

Make a project in the repository root:

```bash
uv run interop
```

Select `init`. At `Target directory?`, type `aetos`. At `Scaffold an example?`, select `none`. Then copy this text into
`aetos/inputs/aetos_mappings.yaml`:

```yaml
osemosys:
  units: {capacity: GW, energy: PJ, currency: USD, currency_year: 2021, emissions: Mt}
  objects:
    fuels:
      - match: "^(?P<country>[A-Z]{2})E[123]$"
        carrier: electricity
        location: "{country}"
      - match: "^(?P<country>[A-Z]{2})NG$"
        carrier: natural-gas
        location: "{country}"
    technologies:
      - match: "^[A-Z]{2}NGCC"
        category: gas-combined-cycle
```

The AETOS `README.md` gives the units. The two `fuels:` rows give each electricity fuel and each
natural gas fuel its carrier, and the country code as its location. The `technologies:` row
marks the combined-cycle gas plants. The
[OSeMOSYS mappings tutorial](../tutorials/osemosys-mappings.md) teaches each part of the file.

## Stage the model

Do this command in the `aetos` directory:

```bash
INTEROP_LOG_LEVEL=WARNING uv run interop headless_cli --pipeline osemosys-csv-to-canonical \
  --override 'source.config_path=../case_study_inputs/aetos/AETOS_Runner/config_otoole_AETOS.yaml' \
  --override 'source.csv_dir=../case_study_inputs/aetos/AETOS_Runner/CSVFiles' \
  --user-mappings-path inputs/aetos_mappings.yaml
```

The run writes the canonical stage to `outputs/canonical/`, and the console shows two warnings:

```
WARNING ... 159 raw table(s) match no canonical parameter by name and key, so each stays an extension table: ATReserveMarginTagTechnology, BEReserveMarginTagTechnology, BGReserveMarginTagTechnology and 156 more
WARNING ... no kind fits 213 technology(ies) in their region, so each keeps an empty kind: REGION1/DZSO00I00, REGION1/EGSO00I00, REGION1/EGWI00I00 and 210 more
```

## What the run gives

We did this run on 2026-10-13.

| Part of the canonical stage | Count |
| --- | --- |
| Sets | 11 |
| Parameters | 54, with 1,024,108 rows in total |
| Extension tables | 159 |
| Technologies with a kind | 2945 of 3158 |
| Fuels with a carrier | 333 of 804: 248 electricity and 85 natural gas |

The canonical schema has no parameter with the name of an extension table, so each of these
tables stays as the model states it:

- 78 tables are `ReserveMarginTagTechnology`, split by country, for example
  `ATReserveMarginTagTechnology`.
- 78 tables are `YearlyPeak`, split by country, for example `YearlyPeakAT`.
- 3 tables are `StorageChargeDuration`, `StorageTag` and `TradeRoute`.

Of the 213 technologies with no kind, 132 are solar, wind and hydro plants. Their names end in
`SO00I00`, `WI00I00` and `HY00I00`. The other 81 are gas pipelines between two countries, for
example `ATNGDEPI0`. A row in `objects:` can give each of them a category.

## What it costs

The run took 2.7 seconds and used 0.4 GB of memory. The canonical stage is 1.6 MB on disk.
