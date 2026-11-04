# Real AGV factory layouts (KIT data set)

Real material-flow and layout data for AGV systems, from the Karlsruhe Institute of Technology (KIT). Our own training data is simulated. This set holds real factory layouts to test the model against.

## Source
M. Sperling, B. Schulz, C. Enke, D. Giebels and K. Furmans, "Classified AGV Material Flow and Layout Data Set for Multidisciplinary Investigation", *IEEE Access*, vol. 11, pp. 94992–95007, 2023. DOI: [10.1109/ACCESS.2023.3308216](https://doi.org/10.1109/ACCESS.2023.3308216)

- Downloaded on 2026-11-04 from the paper's "Supplemental Items" on IEEE Xplore (`access-3308216-mm.zip`, 348,071 bytes). The files are unchanged; the zip's top folder was removed.
- The paper is published under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The data files state no separate license. Cite the paper above wherever this data is used (report, poster, exhibition).

## What is in it
72 folders, one per layout:
- `Industry01`–`Industry30`: real layouts from German industry;
- `Literature01`–`Literature42`: layouts from published research papers.

Each folder has six files:

| File | What it is |
|---|---|
| `*_Stationlist.csv` | stations and their type: `Q` = source (where material is picked up, like our racks), `S` = sink (where it is delivered, like our stations) |
| `*_Transportmatrix.csv` | loaded trips per hour from each station (row) to each station (column) |
| `*_Distancematrix.csv` | driving distance in meters between stations |
| `*_Joblist.csv` | the same trips as a list: start, end, distance (m) and frequency (trips per hour) |
| `*_Emptyrunmatrix.csv` | the fewest empty trips needed to keep the vehicles balanced |
| `*_Totaltransportmatrix.csv` | loaded trips plus empty trips |

The files use **semicolons** as separators and are encoded in **Windows-1252**, not UTF-8. Some names contain German letters. To read them in Python:

```python
pd.read_csv(path, sep=";", encoding="cp1252")
```

## Quick facts (counted from the files)
| | Industry (30) | Literature (42) |
|---|---|---|
| Stations | 2–58 (median 2) | 3–20 (median 8) |
| Source→sink jobs | 1–61 (median 1) | 2–144 (median 9) |
| Trips per hour | 3.2–515 (median 40) | 7–395 (median 45.5) |
| Job distance | 2–340 m | 4–480 m |

**Note:** 18 of the 30 industry layouts are simple shuttles, with one source and one sink, so they have no ordering choice for the AI. The industry layouts with several jobs are the useful ones for testing the dispatcher: 01, 02, 03, 05, 06, 08, 10, 11, 12, 26, 27, 28, 29 and 30.

`agv_brain/real_layouts.py` reads these files, and `scripts/evaluate_real_layouts.py` tests the model on them. The results are in `reports/real_layouts.md`.

Only the layouts and material flows are real. The data has no record of real dispatch decisions, so the right answer for each test situation still comes from our exact optimizer.
