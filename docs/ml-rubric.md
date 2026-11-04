# Rubric for the machine-learning model

The capstone asks for a rubric to judge the machine-learning algorithm. Each criterion is scored from 1 to 4. The last column is where this project stands now. Re-check it after every retraining, using `reports/evaluation.md`.

| Criterion | 4 – Excellent | 3 – Good | 2 – Fair | 1 – Weak | This project |
|---|---|---|---|---|---|
| **Accuracy** (top-1 vs exact optimizer, unseen test situations) | ≥ 90 % | 80–90 % | 65–80 % | < 65 % | 91.6 % → **4** |
| **Accuracy in live operation** (the model running the factory itself) | ≥ 90 % | 80–90 % | 65–80 % | < 65 % | 83.8 % over 1197 live decisions → **3** |
| **Better than simple rules** (top-1 accuracy gap to the best rule) | ≥ +20 points | +10–20 | +3–10 | < +3 | +28.9 over earliest stockout (61.7 %); live: +33.7 → **4** |
| **Effect on the factory** (line-stop time vs first come, first served) | ≥ 40 % less | 25–40 % | 10–25 % | < 10 % | 42 % less → **4** |
| **Generalization: new factory layouts** (accuracy drop on factories never seen) | ≤ 5 points | ≤ 10 | ≤ 20 | > 20 | 91.1 % on 200 new layouts vs 91.6 %: a drop of 0.5 → **4**. On 14 **real** factory layouts (KIT data set, never used for training): 85.6 %, a drop of 6.0, which alone would score 3 |
| **Generalization: more requests than in training** (7 vs 2–6) | ≤ 5 points | ≤ 10 | ≤ 20 | > 20 | 86.1 % vs 92.7 % average, a drop of 6.6 → **3** |
| **Speed** (time per decision on the laptop) | ≤ 20 ms | ≤ 100 ms | ≤ 500 ms | > 500 ms | 20.5 ms mean, 28 ms p95 measured on its own (2026-11-04, with other programs running; the same kind of model measured 9–12 ms on a quiet laptop) → **3** |
| **Dataset quality** (size, labels, balance, held-out test) | ≥ 10k situations, exact labels, balanced, separate test seed | 2 of those weaker | 3 weaker | no held-out test | 30k random situations + 18k live situations + 12k in large factories, exact optimizer labels, 50/50, separate seeds → **4** |
| **Explainability** (can it say why?) | reasons + what-if for every decision + feature importance | reasons only | importance only | none | all three, live on the dashboard → **4** |
| **Robustness / safety** (what happens when the ML is wrong or unsure) | hard safety rules first, optimizer cross-check, fallback policy | 2 of 3 | 1 of 3 | none | safety rules + "optimizer agrees" check + rules fallback → **4** |

**Total: 37 / 40**

Where the three missing points come from:
- **Live operation (84 %):** live queues have many near-ties, and its mistakes are small: on average 0.8 % more cost than the best choice. More rounds of live training (`scripts/train_live.py --rounds 3`) would likely raise it a little more.
- **7 requests at once:** training stops at 6. Training with up to 7–8 would likely fix it.
- **Speed (20.5 ms):** just over the 20 ms line, measured while other programs were busy on the laptop. Re-measure on a quiet laptop before the exhibition: v2 and v3 measured 9–12 ms that way.

## How each number is produced
- Accuracy (offline and live), the rule comparison, factory effect, both generalization rows and speed come from `python scripts/evaluate.py` → `reports/evaluation.md`.
- Real factory layouts: `python scripts/evaluate_real_layouts.py` → `reports/real_layouts.md` (see [dataset.md](dataset.md#real-factory-layouts-test-only)).
- Dataset quality: [dataset.md](dataset.md).
- Explainability: every `Decision` has `reasons` (see `python scripts/demo.py` and the dashboard), and `reports/feature_importance.png` shows which factors matter most.
- Robustness: `agv_brain/safety.py` checks warehouse stock, room for a box, reachability and battery before the ML is asked. Every decision is compared with the exact optimizer, and the dashboard shows it.

## History
| Version | Training data | Trees | Our track | New layouts | Live operation |
|---|---|---|---|---|---|
| 1 | 20k random situations, our track | ~400 | 91.0 % | 91.3 % | – |
| 2 | 30k random situations, our track + 400 random layouts | 800 | 91.5 % | 91.3 % | 76.0 % |
| 3 | v2 data + 18k live situations (2 DAgger rounds) | 800 | 90.6 % | 91.2 % | **84.2 %** |
| 4 (current) | v3 data + 12k situations in 300 large random factories | 800 | 91.6 % | 91.1 % | 83.8 % |

Real factories (KIT data set, `scripts/evaluate_real_layouts.py`): version 3 scored 83.2 %, version 4 scores **85.6 %**.

Versions 2, 3 and 4 take the same time per decision (v2 and v3: about 9 ms side by side; v3 and v4: 21 and 20 ms side by side on a busier day). Version 1, with half the trees, took about half the time.

Lessons, for the report:
- The model only sees times and numbers, never names, so it already worked on new layouts. Training on random layouts mainly confirmed that.
- Running the factory live showed a gap the offline tests had hidden: 76 % live against 91 % offline. Training on the situations the model actually meets (DAgger) closed most of it, without hurting the offline results.
- Testing on real factories showed a gap the simulation had hidden: 83.2 % against 91 %, because real factories are much bigger (up to 340 m) than our table-top track. Adding large random factories with the same general sizes to training raised it to 85.6 %. The 14 real factories themselves were never trained on, so they stay a fair test. The rule for keeping version 4 was set before testing: better on the real factories, and no other result more than 1 point worse. Live operation moved from 84.2 % to 83.8 %, which is within chance.
- Decision times depend on how busy the laptop is (the same model measured 9 ms and 20 ms on different runs). To compare two models, time them side by side in the same run.
