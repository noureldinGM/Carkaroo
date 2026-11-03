# Dataset

The capstone asks for the dataset used by the machine-learning model. This is how it is made and what is in it.

## Where the data comes from
There is no factory history to learn from yet, so the data is **simulated**, and every example is labelled by an **exact optimizer** (the "teacher"):

1. `agv_brain/simulator.py` creates a random factory situation:
   - the car at a random node and heading;
   - 2 to 6 open requests, each a (station, material) pair;
   - per request: a usage rate of 0.5–6 units/min and a time until empty. Time until empty is 30 % urgent (0–60 s), 40 % medium (60–240 s) and 30 % relaxed (4–15 min);
   - a safety stock worth 30–150 s of usage;
   - a station criticality of 1–3;
   - a waiting time (exponential, mean 60 s);
   - a car speed of 0.6×, 0.8×, 1×, 1.2× or 1.5× the configured speed, so the model still works after the real car is calibrated.
2. `agv_brain/optimizer.py` tries every possible order and computes, for each request, the best total cost if that request goes first. The cost counts line-stop seconds × criticality, time below safety stock, waiting, and driving time; see `config/materials.yaml` → `cost`.
3. `agv_brain/ranker.py` turns each situation into **pairs**: "should request i go before request j?" The label is 1 if starting with i gives a lower best cost than starting with j. Exact ties are skipped.

Regenerate it with:
```bash
python scripts/generate_dataset.py --scenarios 20000 --seed 1
```

## Files
| File | In git | What it is |
|---|---|---|
| `data/sample/requests_sample.csv` | yes | first 300 situations, one row per request (readable, for the exhibition) |
| `data/generated/requests.csv` | no | all situations, one row per request |
| `data/generated/pairs.npz` | no | the training matrix: `X` (pair features), `y` (labels), `w` (weights), `groups` (situation id) |

Size of the default dataset: 20,000 situations, about 80,000 requests and about 280,000 pairs with 47 features each. The labels are balanced (50 % / 50 %).

## Columns of `requests_sample.csv`
| Column | Meaning |
|---|---|
| `scenario` | situation id (all requests with the same id were waiting at the same time) |
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

## Train / test split
- Training holds out 20 % of the situations, whole situations at a time, for validation (`scripts/train_ranker.py`).
- The final test uses 1000 **new** situations from a different random seed. They have up to **7** requests, while training used at most 6 (`scripts/evaluate.py`).
