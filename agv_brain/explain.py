"""Human-readable reasons for a decision, including "what if" comparisons."""

from __future__ import annotations

from agv_brain.models import CarState, Job
from agv_brain.need_detector import fmt_s
from agv_brain.optimizer import MAX_EXACT, best_order_starting_with, first_choice_costs
from agv_brain.simulator import Context, Schedule, job_leg, simulate

SAME = 0.5  # cost differences below this are reported as "about the same"


def label(ctx: Context, job: Job) -> str:
    st = ctx.settings.stations[job.station]
    return f"{job.material} -> {job.station} ({st.name})"


def explain(ctx: Context, jobs: list[Job], car: CarState, plan: Schedule) -> list[str]:
    if not plan.tasks:
        return ["Nothing to deliver right now."]
    first = plan.tasks[0].job
    leg = job_leg(ctx, car, first)
    lines = [
        f"Go first: {label(ctx, first)}. It has {max(first.stock, 0):.0f} units left and runs out in "
        f"{fmt_s(first.stockout_s)}; the trip takes {fmt_s(leg.duration_s)} "
        f"(criticality {first.criticality})."
    ]
    if len(jobs) < 2:
        return lines
    if len(jobs) > MAX_EXACT:
        lines.append(f"{len(jobs)} requests: too many for the exact what-if check, "
                     "using the ML order only.")
        return lines

    stops_now = plan.stop_by_job()
    for k, other in enumerate(jobs):
        if other.id == first.id:
            continue
        alt = simulate(ctx, best_order_starting_with(ctx, jobs, car, k), car)
        stops_alt = alt.stop_by_job()
        deltas = [(j, stops_alt[j.id] - stops_now.get(j.id, 0.0)) for j in jobs]
        diff = alt.total_cost - plan.total_cost
        head = f"If {label(ctx, other)} went first instead: "
        if diff >= SAME:
            worse = [f"{j.station} would stop {fmt_s(d)} longer" for j, d in deltas if d > 0.5]
            if worse:
                lines.append(head + ", ".join(worse) + f" (cost +{diff:.0f}).")
            else:
                lines.append(head + "no line would stop, but stations stay below safety stock "
                             f"longer or the car drives more (cost +{diff:.0f}).")
        elif diff <= -SAME:
            better = [f"{j.station} would stop {fmt_s(-d)} less" for j, d in deltas if d < -0.5]
            lines.append(head + "that would be better" + (": " + ", ".join(better) if better else "")
                         + f" (cost {diff:.0f}).")
        else:
            lines.append(head + "about the same result.")

    costs = first_choice_costs(ctx, jobs, car)
    best = min(range(len(jobs)), key=costs.__getitem__)
    chosen = next(i for i, j in enumerate(jobs) if j.id == first.id)
    if costs[chosen] >= costs[best] + SAME:
        lines.append(f"Note: the exact optimizer would start with {label(ctx, jobs[best])} "
                     f"(its plan costs {costs[best]:.0f} vs {costs[chosen]:.0f}).")
    elif costs[chosen] > costs[best] + 1e-6:
        lines.append(f"The exact optimizer slightly prefers {label(ctx, jobs[best])}, but the "
                     f"difference is tiny ({costs[chosen] - costs[best]:.2f}): practically a tie.")
    else:
        lines.append("The exact optimizer agrees with this choice.")
    return lines
