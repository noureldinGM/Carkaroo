# Dataset

The capstone asks for the dataset used by the machine-learning model. This is how it is made and what is in it.

## Where the data comes from
There is no factory history to learn from yet, so the data is **simulated**, and every example is labelled by an **exact optimizer** (the "teacher"):

1. `agv_brain/simulator.py` creates a random factory situation, either on our track (`config/factory_layout.yaml`, 40 %) or on one of 400 **random factory layouts** (`agv_brain/layouts.py`, 60 %). A random layout has:
   - a grid of 2–4 × 3–6 junctions, lines of 50–150 cm, and a few lines removed;
   - 2–5 materials, 2–6 stations, and a dock on line ends around the outside;
   - only junctions the IR sensors can detect (T, cross or L corner).

   On whichever track it picked, it then places:
   - the car at a random node and heading;
   - 2 to 6 open requests, each a (station, material) pair;
   - per request: a usage rate of 0.5–6 units/min and a time until empty. Time until empty is 30 % urgent (0–60 s), 40 % medium (60–240 s) and 30 % relaxed (4–15 min);
   - a safety stock worth 30–150 s of usage;
   - a station criticality of 1–3;
   - a waiting time (exponential, mean 60 s);
   - a car speed between 0.6× and 1.5× the configured speed, so the model still works after the real car is calibrated.
2. `agv_brain/optimizer.py` tries every possible order and computes, for each request, the best total cost if that request goes first. The cost counts line-stop seconds × criticality, time below safety stock, waiting, and driving time; see `config/materials.yaml` → `cost`.
3. `agv_brain/ranker.py` turns each situation into **pairs**: "should request i go before request j?" The label is 1 if starting with i gives a lower best cost than starting with j. Exact ties are skipped.

Regenerate it with:
```bash
python scripts/generate_dataset.py --scenarios 30000 --random-layouts 400 --layout-share 0.6
```

## Files
| File | In git | What it is |
|---|---|---|
| `data/sample/requests_sample.csv` | yes | first 300 situations, one row per request (readable, for the exhibition) |
| `data/generated/requests.csv` | no | all situations, one row per request |
| `data/generated/pairs.npz` | no | the training matrix: `X` (pair features), `y` (labels), `w` (weights), `groups` (situation id) |

Size of the default dataset: 30,000 situations, 119,343 requests and 413,888 pairs with 47 features each. The labels are balanced (50 % / 50 %).

## Columns of `requests_sample.csv`
| Column | Meaning |
|---|---|
| `scenario` | situation id (all requests with the same id were waiting at the same time) |
| `layout` | `ours` (our track) or `random-<k>` (one of the random factories) |
| `request` | material@station |
| `car_node`, `car_heading`, `car_speed_cm_s` | where the car was, which way it faced, how fast it drives |
| `material`, `station` | what is needed where |
| `stock` | units left at the station |
| `rate_per_min` | usage rate (units/min) |
| `stockout_s` | seconds until the station runs out |
| `below_safety_s` | seconds until the stock drops below the safety level |
| `trip_s` | seconds to drive to the rack, lift, drive to the station and lower |
| `to_rack_s` | seconds to reach the rack |
| `slack_s` | `stockout_s - trip_s` (negative = the line stops even if served now) |
| `safety_slack_s` | `below_safety_s - trip_s` |
| `criticality` | 1 = can wait, 3 = bottleneck line |
| `wait_s` | how long the request has been waiting |
| `safety_gap` | how far below safety stock (0 = not below, 1 = empty) |
| `n_jobs` | requests waiting at the same time |
| `slack_rank` | 0 = tightest slack of the group, 1 = loosest |
| `min_other_slack_s` | tightest slack among the other requests |
| `teacher_cost_if_first` | best total cost the optimizer finds if this request goes first |
| `teacher_best_first` | 1 if this request is the optimizer's best first choice (the label to predict) |

A pair row in `pairs.npz` holds the features of i, the features of j, and their difference (i − j). It adds five pair features: the finish time of each request if the other goes first, how long each would stop the line, and the criticality-weighted difference of those stops.

## Live-operation data (DAgger)
Random situations don't look like the queues the AI meets when the factory actually runs. `scripts/train_live.py` runs the factory quickly with the current model making the decisions (20 % random choices), on our track and on random layouts. It labels every decision situation with the exact optimizer and retrains on everything collected so far. Two rounds added 18,231 live situations (338,650 pairs).

| File | In git | What it is |
|---|---|---|
| `data/sample/live_requests_sample.csv` | yes | the first 300 live situations, one row per request (same columns as above, plus `round`) |
| `data/generated/live_requests.csv`, `live_pairs.npz` | no | all live situations and their training pairs |

## Train / test split
- Training holds out 20 % of the situations, whole situations at a time, for validation (`scripts/train_ranker.py`).
- The final test (`scripts/evaluate.py`) uses different random seeds from training, with up to **7** requests per situation (training used at most 6). It has two parts:
  - 1000 new situations on our track;
  - 1000 situations on 200 **factory layouts the model has never seen**;
  - 40 one-hour **live factory runs** with the model making every decision (about 1400 decisions checked).
