# CSKG Graph Database

This repository contains a local ArangoDB-based implementation for querying the CSKG dataset.

## Requirements

Install the following before running the project:

- Python 3.9 or newer
- Docker Desktop
- Python packages:

```bash
pip install python-arango tqdm
```

## Clone the repository

```bash
git clone https://gitlab.kis.agh.edu.pl/databases-2-2026/9-stralchonak-wilczynski.git
cd 9-stralchonak-wilczynski
```

## Run locally with Docker

1. Make sure Docker Desktop is running.
2. Place `cskg.tsv` in the project root if you want to import the dataset.
3. Start the local environment:

```powershell
.\setup_env.ps1
```

This script will:

- check Docker
- start or create the ArangoDB container
- wait for the database to become ready
- import the CSKG data from `cskg.tsv`

If you only want to start the container without importing data, run:

```powershell
.\setup_env.ps1 -SkipImport
```

If the data is already loaded and you want to reuse it, you can then run queries such as:

```bash
python cskg_cli.py 9
python cskg_cli.py successors /c/en/dog
python cskg_cli.py 18 /c/en/rollercoaster 17 --count-time
```

## Documentation

The full implementation description, schema notes, query explanations, and performance details are in [DOCUMENTATION.md](DOCUMENTATION.md).
