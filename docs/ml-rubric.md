# Rubric for the machine-learning model

The capstone asks for a rubric to judge the machine-learning algorithm. Each criterion is scored from 1 to 4. The last column is where this project stands now. Re-check it after every retraining, using `reports/evaluation.md`.

| Criterion | 4 – Excellent | 3 – Good | 2 – Fair | 1 – Weak | This project |
|---|---|---|---|---|---|
| **Accuracy** (top-1 vs exact optimizer, unseen data) | ≥ 90 % | 80–90 % | 65–80 % | < 65 % | 91.2 % → **4** |
| **Better than simple rules** (top-1 accuracy gap to the best rule) | ≥ +20 points | +10–20 | +3–10 | < +3 | +29.4 over earliest stockout (61.8 %) → **4** |
| **Effect on the factory** (line-stop time vs first come, first served) | ≥ 40 % less | 25–40 % | 10–25 % | < 10 % | 42 % less → **4** |
| **Generalization** (situations unlike training: more requests, other car speeds) | accuracy drop ≤ 5 points | ≤ 10 | ≤ 20 | > 20 | 7 requests (never seen): 86.1 % vs 92.3 % average for 2–6, a drop of 6.2 → **3** |
| **Speed** (time per decision on the laptop) | ≤ 20 ms | ≤ 100 ms | ≤ 500 ms | > 500 ms | about 5 ms → **4** |
| **Dataset quality** (size, labels, balance, held-out test) | ≥ 10k situations, exact labels, balanced, separate test seed | 2 of those weaker | 3 weaker | no held-out test | 20k, exact optimizer labels, 50/50, separate seed → **4** |
| **Explainability** (can it say why?) | reasons + what-if for every decision + feature importance | reasons only | importance only | none | all three → **4** |
| **Robustness / safety** (what happens when the ML is wrong or unsure) | hard safety rules first, optimizer cross-check, fallback policy | 2 of 3 | 1 of 3 | none | safety rules + "optimizer agrees" check + rules fallback → **4** |

**Total: 31 / 32** (the generalization row is the one to improve). Ideas for that: train with up to 7 requests, or add sensor noise during training.

## How each number is produced
- Accuracy, the rule comparison, factory effect, generalization and speed come from `python scripts/evaluate.py --scenarios 1000` → `reports/evaluation.md`.
- Dataset quality: [dataset.md](dataset.md).
- Explainability: every `Decision` has `reasons` (see `python scripts/demo.py`), and `reports/feature_importance.png` shows which factors matter most.
- Robustness: `agv_brain/safety.py` checks warehouse stock, room for a box, reachability and battery before the ML is asked. `explain.py` compares the ML choice with the exact optimizer every time.
