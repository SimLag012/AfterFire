from typing import List, Dict, Any, Optional
from datetime import datetime, date
import numpy as np


class RecurrenceEngine:
    """
    Engine for analyzing recurrent fire disturbances on the same territory.
    Detects re-burns, calculates return intervals, and tracks whether vegetation
    had approached pre-fire baseline before the subsequent fire occurred.
    """

    @classmethod
    def analyze_recurrence(
        cls,
        area_id: str,
        area_name: str,
        events: List[Dict[str, Any]],
        vegetation_obs: List[Dict[str, Any]],
        pre_fire_baseline: float = 0.65
    ) -> Dict[str, Any]:
        """
        Evaluates return intervals and recovery state between successive fire events.
        """
        sorted_events = sorted(
            events,
            key=lambda e: e["start_date"] if isinstance(e["start_date"], date) else datetime.strptime(str(e["start_date"])[:10], "%Y-%m-%d").date()
        )

        event_items = []
        return_intervals = []

        # Map vegetation by date
        valid_veg = sorted(
            [v for v in vegetation_obs if v.get("is_valid", True)],
            key=lambda v: v["observation_date"] if isinstance(v["observation_date"], date) else datetime.strptime(str(v["observation_date"])[:10], "%Y-%m-%d").date()
        )

        for i, ev in enumerate(sorted_events):
            ev_start = ev["start_date"] if isinstance(ev["start_date"], date) else datetime.strptime(str(ev["start_date"])[:10], "%Y-%m-%d").date()
            
            days_since_prev = None
            if i > 0:
                prev_ev = sorted_events[i - 1]
                prev_start = prev_ev["start_date"] if isinstance(prev_ev["start_date"], date) else datetime.strptime(str(prev_ev["start_date"])[:10], "%Y-%m-%d").date()
                days_since_prev = max(0, (ev_start - prev_start).days)
                return_intervals.append(days_since_prev)

            # Find closest vegetation prior to this event
            prior_veg = [
                v for v in valid_veg
                if (v["observation_date"] if isinstance(v["observation_date"], date) else datetime.strptime(str(v["observation_date"])[:10], "%Y-%m-%d").date()) < ev_start
            ]
            
            pre_val = float(prior_veg[-1]["scaled_value"]) if prior_veg else pre_fire_baseline
            
            # Post-fire vegetation
            post_veg = [
                v for v in valid_veg
                if (v["observation_date"] if isinstance(v["observation_date"], date) else datetime.strptime(str(v["observation_date"])[:10], "%Y-%m-%d").date()) >= ev_start
            ]
            post_min = min([float(v["scaled_value"]) for v in post_veg[:4]]) if post_veg else (pre_val * 0.5)
            ndvi_drop = round(max(0.0, pre_val - post_min), 3)

            recovered_before_next = None
            rec_status = None
            if i < len(sorted_events) - 1:
                next_ev = sorted_events[i + 1]
                next_start = next_ev["start_date"] if isinstance(next_ev["start_date"], date) else datetime.strptime(str(next_ev["start_date"])[:10], "%Y-%m-%d").date()
                inter_veg = [
                    v for v in valid_veg
                    if ev_start < (v["observation_date"] if isinstance(v["observation_date"], date) else datetime.strptime(str(v["observation_date"])[:10], "%Y-%m-%d").date()) < next_start
                ]
                if inter_veg:
                    max_inter = max([float(v["scaled_value"]) for v in inter_veg])
                    rec_ratio = max_inter / pre_fire_baseline
                    recovered_before_next = rec_ratio >= 0.85
                    rec_status = "Substantially Recovered" if rec_ratio >= 0.85 else "Truncated / Interrupted Recovery"
                else:
                    recovered_before_next = False
                    rec_status = "Insufficient Inter-Fire Observations"

            event_items.append({
                "event_id": ev["id"],
                "event_name": ev.get("name", f"Fire Event {ev_start.strftime('%Y')}"),
                "start_date": ev_start.strftime("%Y-%m-%d"),
                "end_date": str(ev.get("end_date", ev_start))[:10],
                "detection_count": ev.get("detection_count", 0),
                "days_since_previous_event": days_since_prev,
                "pre_event_ndvi": round(pre_val, 3),
                "ndvi_drop": ndvi_drop,
                "did_recover_before_next": recovered_before_next,
                "recovery_status_at_next": rec_status
            })

        mean_interval = round(float(np.mean(return_intervals)), 1) if return_intervals else None

        if len(sorted_events) <= 1:
            risk = "Single documented event in analyzed window"
            interp = "No historical recurrence detected in this temporal extent. Single disturbance baseline."
        else:
            interrupted_count = sum(1 for item in event_items if item["did_recover_before_next"] is False)
            if interrupted_count > 0:
                risk = "Compound disturbance / High recurrence pressure"
                interp = f"Observed {len(sorted_events)} fire clusters within the record. In {interrupted_count} occurrence(s), a subsequent thermal activity cluster was detected before canopy greenness recovered to pre-disturbance baseline levels, suggesting potential recovery delay or ecological state transition."
            else:
                risk = "Moderate recurrence with cyclical regrowth"
                interp = f"Multiple fire clusters observed with average return interval of {mean_interval} days ({round(mean_interval/365, 1)} years). Canopy greenness showed substantial recovery prior to subsequent detected events."

        limitations = [
            "Thermal hotspot recurrence does not confirm that 100% of the internal polygon re-burned identically; unburned islands may burn in subsequent passes.",
            "Short-interval re-burns frequently alter vegetative regeneration trajectories from tree dominance to pyrophytic shrublands.",
            "Satellite resolution constraints mean low-intensity ground fires under unconsumed canopies may escape detection."
        ]

        return {
            "area_id": area_id,
            "area_name": area_name,
            "total_events": len(sorted_events),
            "mean_return_interval_days": mean_interval,
            "events": event_items,
            "recurrent_risk_assessment": risk,
            "scientific_interpretation": interp,
            "limitations": limitations
        }

