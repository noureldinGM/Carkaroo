# Rubric for the machine-learning model

The capstone asks for a rubric to judge the machine-learning algorithm. Each criterion is scored from 1 to 4. The last column is where this project stands now. Re-check it after every retraining, using `reports/evaluation.md`.

| Criterion | 4 – Excellent | 3 – Good | 2 – Fair | 1 – Weak | This project |
|---|---|---|---|---|---|
| **Accuracy** (top-1 vs exact optimizer, unseen data) | ≥ 90 % | 80–90 % | 65–80 % | < 65 % | 91.5 % → **4** |
| **Better than simple rules** (top-1 accuracy gap to the best rule) | ≥ +20 points | +10–20 | +3–10 | < +3 | +29.8 over earliest stockout (61.7 %) → **4** |
| **Effect on the factory** (line-stop time vs first come, first served) | ≥ 40 % less | 25–40 % | 10–25 % | < 10 % | 42 % less → **4** |
| **Generalization: new factory layouts** (accuracy drop on factories never seen) | ≤ 5 points | ≤ 10 | ≤ 20 | > 20 | 91.3 % on 200 new layouts vs 91.5 %, a drop of 0.2 → **4** |
| **Generalization: more requests than in training** (7 vs 2–6) | ≤ 5 points | ≤ 10 | ≤ 20 | > 20 | 86.7 % vs 92.5 % average, a drop of 5.8 → **3** |
| **Speed** (time per decision on the laptop) | ≤ 20 ms | ≤ 100 ms | ≤ 500 ms | > 500 ms | about 20 ms mean, p95 under 35 ms → **3** |
| **Dataset quality** (size, labels, balance, held-out test) | ≥ 10k situations, exact labels, balanced, separate test seed | 2 of those weaker | 3 weaker | no held-out test | 30k situations on our track + 400 random layouts, exact optimizer labels, 50/50, separate seeds → **4** |
| **Explainability** (can it say why?) | reasons + what-if for every decision + feature importance | reasons only | importance only | none | all three → **4** |
| **Robustness / safety** (what happens when the ML is wrong or unsure) | hard safety rules first, optimizer cross-check, fallback policy | 2 of 3 | 1 of 3 | none | safety rules + "optimizer agrees" check + rules fallback → **4** |

**Total: 34 / 36**

Where the two missing points come from:
- **More requests than in training:** training stops at 6 requests at once. Training with up to 7–8 would likely fix it.
- **Speed:** training on 400 random layouts made the model twice as big (800 trees instead of about 400). Each decision now takes about 20 ms instead of about 11 ms on the same laptop. That is still 5× under the 100 ms requirement, and the car only decides once per delivery, so it was worth the better coverage of new tracks. A model with fewer trees or a faster laptop would get this point back.

## How each number is produced
- Accuracy, the rule comparison, factory effect, both generalization rows and speed come from `python scripts/evaluate.py` → `reports/evaluation.md`.
- Dataset quality: [dataset.md](dataset.md).
- Explainability: every `Decision` has `reasons` (see `python scripts/demo.py`), and `reports/feature_importance.png` shows which factors matter most.
- Robustness: `agv_brain/safety.py` checks warehouse stock, room for a box, reachability and battery before the ML is asked. `explain.py` compares the ML choice with the exact optimizer every time, and says so when they disagree.

## History
| Version | Training data | Our track | New layouts | Decision time |
|---|---|---|---|---|
| 1 | 20k situations, our track only | 91.0 % | 91.3 % | ~11 ms |
| 2 (current) | 30k situations, our track + 400 random layouts | 91.5 % | 91.3 % | ~20 ms |

Both rows were measured on the same test sets and the same laptop. The first model already did well on new layouts, because it only sees times, never names. Training on random layouts mainly confirms the result, and makes sure the training data covers whatever shape the real track has.
