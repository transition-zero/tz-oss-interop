# Synched case study inputs

Put the published models in this directory. Git ignores all the files in this directory
except this file.

This table tells you where to get each model and where to put it.

| Put it in | Model | Get it from |
| --- | --- | --- |
| `aetos/` | AETOS (Africa–Europe Energy Transition OSeMOSYS), version `v2.0.0` | [GitHub tag `v2.0.0`](https://github.com/ekousoulos/AETOS-model/tree/v2.0.0) or [Zenodo record 18479411](https://doi.org/10.5281/zenodo.18479411) |

## AETOS

The AETOS repository holds the model inputs, so you can clone the tag:

```sh
git clone --depth 1 --branch v2.0.0 https://github.com/ekousoulos/AETOS-model.git case_study_inputs_synched/aetos
rm -rf case_study_inputs_synched/aetos/.git
```

You can also download the archive from Zenodo. The archive is 98.4 MB.

```sh
curl -L -o /tmp/aetos-v2.0.0.zip "https://zenodo.org/records/18479411/files/ekousoulos/AETOS-model-v2.0.0.zip?download=1"
md5sum /tmp/aetos-v2.0.0.zip
```

The checksum must be `76bcfbe64fe92f36d7dffc2993f50a9f`. Extract the archive. Then move
the top-level directory of the archive to `case_study_inputs_synched/aetos/`.

Do not change the directory layout of the publisher. The model inputs are in
`aetos/AETOS_Runner/`:

- `CSVFiles/` holds one CSV file for each OSeMOSYS parameter and set.
- `input_data/` holds one Excel workbook for each scenario.
- `config_otoole_AETOS.yaml` is the otoole configuration for the CSV files.

The model is licensed under the MIT licence. Cite it as the AETOS `README.md` says.
