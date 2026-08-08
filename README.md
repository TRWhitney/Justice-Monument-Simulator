# Justice Monument Simulator

Simulator and advisor for the Idleon Justice Monument minigame. Provides both a Qt GUI and an interactive Rich CLI, backed by a shared simulation engine and JSON-driven data.

## Install and Run

No programming tools are required beforehand. The steps below install
[uv](https://docs.astral.sh/uv/getting-started/installation/), which downloads
the required version of Python and keeps this app's packages separate from the
rest of your computer. You need an internet connection during the first setup.

First, [download the app as a ZIP
file](https://github.com/TRWhitney/Justice-Monument-Simulator/archive/refs/heads/main.zip)
and extract it. The extracted folder is normally named
`Justice-Monument-Simulator-main`.

### Windows 10 or 11

1. Open the Start menu, type `PowerShell`, and open **Windows PowerShell**.
2. Copy the following command, paste it into PowerShell, and press Enter:

   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

3. Close PowerShell after the installation finishes. Open the extracted app
   folder in File Explorer, click the address bar, type `powershell`, and press
   Enter. This opens a new PowerShell window in the correct folder.
4. Install the app and its requirements:

   ```powershell
   uv sync
   ```

   uv automatically downloads Python 3.12 or newer if it is not already
   installed. The first setup may take a few minutes.
5. Start the graphical app:

   ```powershell
   uv run justice-sim-gui
   ```

Keep the PowerShell window open while using the app. To run the app again
later, open PowerShell in the same folder and repeat only the final command.

### Linux

1. Open a terminal and install uv with one of these commands. Use the `wget`
   version only if the `curl` command is unavailable:

   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

   ```bash
   wget -qO- https://astral.sh/uv/install.sh | sh
   ```

2. Close and reopen the terminal so that it can find uv.
3. Open the extracted app folder in your file manager, right-click inside the
   folder, and choose **Open in Terminal**. If that option is unavailable, open
   a terminal and use `cd` followed by the folder's path.
4. Install the app and its requirements:

   ```bash
   uv sync
   ```

   uv automatically downloads Python 3.12 or newer if it is not already
   installed. The first setup may take a few minutes.
5. Start the graphical app:

   ```bash
   uv run justice-sim-gui
   ```

Keep the terminal open while using the app. To run the app again later, open a
terminal in the same folder and repeat only the final command.

### Command-Line Version

Windows and Linux users can run the text-based version instead of the graphical
app:

```bash
uv run justice-sim
```

### Setup Troubleshooting

- If `uv` is reported as an unknown or missing command, close every terminal or
  PowerShell window, open a new one, and try `uv --version`. If it is still
  missing, run the uv installer again and follow any PATH instructions it
  prints.
- If uv says it cannot find `pyproject.toml`, the terminal is in the wrong
  folder. Reopen it inside the extracted `Justice-Monument-Simulator-main`
  folder.
- The Linux GUI requires a graphical desktop. Most desktop distributions
  already include Qt's system libraries. On Debian or Ubuntu, if startup fails
  with an error mentioning the `xcb` platform plugin or `libxcb-cursor.so.0`,
  run `sudo apt update && sudo apt install libxcb-cursor0`, then try again. See
  the [Qt Linux/X11 requirements](https://doc.qt.io/qt-6/linux-requirements.html)
  for other distributions or missing-library messages.

Optional GUI launch overrides:

```bash
uv run justice-sim-gui --theme dark --ui-scale large --prompt-tour
```

## GUI Notes

- Bottom-left buttons toggle theme and UI scale (Auto/Small/Medium/Large).
- Theme and UI scale persist between runs.
- Guided tour appears once until dismissed or completed.
- Hold a resource's `-` or `+` button to adjust it repeatedly at increasing speed.
- Use the NPC shortcut row's circle-slash button to clear the active offer filter.
- Unfiltered offers show their deal-luck rank among the encounters currently possible; the run indicator summarizes recorded deal rankings.
- Recommendation utility includes a 95% confidence interval; close calls automatically receive additional rollouts under the builtin planner defaults.

## CLI Notes

- Type `help` for commands.
- Typical flow: `search offer`, `select 1`, `recommend`, `apply best`.
- Use `show-all on/off` to ignore offer conditions (when allowed).
- Switch sim modes with `sim full|mid|none` (manual randomness uses `choose`/`value`).
- Inspect history with `log` and `log show 1`.

## Tests

```bash
uv run pytest -m "unit"
uv run pytest -m "gui"
```

## Validation

```bash
./scripts/validate_repo.sh
```

The full gate checks Ruff formatting and linting, validates both builtin JSON
datasets against their schemas, runs unit and native Qt GUI tests, and performs a
smoke launch.

## Data Validation

```bash
uv run python scripts/validate_schema.py \
  --schema src/justice_sim/data/schema/justice_data.schema.json \
  --instance src/justice_sim/data/builtin/justice_data.json \
  --format

uv run python scripts/validate_schema.py \
  --schema src/justice_sim/data/schema/suggested_rules.schema.json \
  --instance src/justice_sim/data/builtin/suggested_rules.json \
  --format
```

Known questions that the available public data cannot settle are tracked in
[Justice Monument Data: Open Questions](docs/justice-data-open-questions.md).
The simulation methodology and evidence behind the tuned recommendation rules
are recorded in
[Suggested Rules Simulation Analysis](docs/suggested-rules-analysis.html).

## License

This project is released into the public domain under the
[Unlicense](UNLICENSE).
