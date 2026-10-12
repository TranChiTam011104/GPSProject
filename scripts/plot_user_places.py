"""Map one user's home / office / POIs from v1 and v2, for review and reports.

Every number comes from ``src/``: the classifiers are built from settings (as the API does), the
home / office / POI answers are their ``ClassificationResult``, and the per-stay window minutes and
v2 places use the same ``window_minutes`` / ``place_labels`` the classifiers use.

Usage::

    python scripts/plot_user_places.py --candidates            # users with home + office in v1 and v2
    python scripts/plot_user_places.py --user 068              # map + summary for one user
    python scripts/plot_user_places.py --user 068 --no-trajectory

Writes ``data/reports/user_{id}/map.html`` (folium, layers can be switched on/off) and
``summary.json`` (the same data, for the claude.ai report page). ``data/`` is git-ignored: the
outputs hold a real person's home and office. Requires ``folium`` and ``matplotlib`` (dev extra).
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from gps.config.settings import get_settings  # noqa: E402
from gps.data.timezone import local_times  # noqa: E402
from gps.models.base import coerce_stay_points  # noqa: E402
from gps.models.cluster import ClusterClassifier, place_labels  # noqa: E402
from gps.models.heuristic import HeuristicClassifier  # noqa: E402
from gps.utils.geo import haversine_meters  # noqa: E402

STAYPOINT_DIR = ROOT / "data" / "processed" / "staypoints"
USER_DIR = ROOT / "data" / "processed" / "users"
REPORT_DIR = ROOT / "data" / "reports"
MAX_TRAJECTORY_POINTS = 20_000
MIN_HOME_OFFICE_KM = 1.0
MIN_SUPPORT_DAYS = 5
SAME_PLACE_M = 200.0
# Esri tiles need no API key and no Referer (OSM's own tiles refuse a file:// page, CARTO needs a key).
ESRI_TILES = "https://server.arcgisonline.com/ArcGIS/rest/services/{}/MapServer/tile/{{z}}/{{y}}/{{x}}"
BASE_LAYERS = {"streets": "World_Street_Map", "satellite": "World_Imagery"}


def build_classifiers() -> tuple[HeuristicClassifier, ClusterClassifier]:
    settings = get_settings()
    config = settings.classification.model_dump()
    return HeuristicClassifier(config), ClusterClassifier({**config, **settings.clustering.model_dump()})


def load_stays(user_id: str, min_duration_minutes: float):
    df = pd.read_parquet(STAYPOINT_DIR / f"user_{user_id}.parquet")
    return [sp for sp in coerce_stay_points(df.to_dict("records")) if sp.duration_minutes >= min_duration_minutes]


def _distance_m(a, b) -> float:
    return haversine_meters(a.lat, a.lon, b.lat, b.lon)


# ── Candidate users ──────────────────────────────────────────────────────────


def list_candidates(v1: HeuristicClassifier, v2: ClusterClassifier) -> pd.DataFrame:
    """Users whose home and office are found by both versions, home and office apart, enough days."""
    rows = []
    for path in sorted(STAYPOINT_DIR.glob("user_*.parquet")):
        user_id = path.stem.removeprefix("user_")
        stays = load_stays(user_id, v1.min_duration_minutes)
        r1, r2 = v1.predict(stays), v2.predict(stays)
        if not (r1.home and r1.office and r2.home and r2.office):
            continue
        rows.append({
            "user_id": user_id,
            "stays": len(stays),
            "home_office_km": _distance_m(r2.home, r2.office) / 1000.0,
            "v2_home_days": r2.home_status.support,
            "v2_office_days": r2.office_status.support,
            "v2_home_conf": r2.home.confidence,
            "v2_office_conf": r2.office.confidence,
            "v1_v2_home_m": _distance_m(r1.home, r2.home),
            "v1_v2_office_m": _distance_m(r1.office, r2.office),
        })
    df = pd.DataFrame(rows)
    df = df[(df.home_office_km >= MIN_HOME_OFFICE_KM)
            & (df.v2_home_days >= MIN_SUPPORT_DAYS) & (df.v2_office_days >= MIN_SUPPORT_DAYS)]
    df = df.assign(v1_equals_v2=(df.v1_v2_home_m <= SAME_PLACE_M) & (df.v1_v2_office_m <= SAME_PLACE_M))
    return df.sort_values(["v1_equals_v2", "v2_office_days", "v2_home_days"], ascending=False)


# ── One user's summary ───────────────────────────────────────────────────────


def _hourly_minutes(stays_local, work_days) -> dict[str, list[float]]:
    """Minutes at a place per local hour of day, split into work days and other days."""
    out = {"workday": [0.0] * 24, "other": [0.0] * 24}
    for arrival, departure in stays_local:
        t = arrival
        while t < departure:
            step_end = min(departure, t.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
            kind = "workday" if t.weekday() in work_days else "other"
            out[kind][t.hour] += (step_end - t).total_seconds() / 60.0
            t = step_end
    return out


def _location_dict(loc) -> dict | None:
    if loc is None:
        return None
    d = loc.to_dict()
    d["first_seen"] = d["first_seen"].isoformat() if d["first_seen"] else None
    d["last_seen"] = d["last_seen"].isoformat() if d["last_seen"] else None
    return d


def _result_dict(result) -> dict:
    return {
        "model_version": result.model_version,
        "home": _location_dict(result.home),
        "office": _location_dict(result.office),
        "home_status": vars(result.home_status),
        "office_status": vars(result.office_status),
        "pois": [_location_dict(p) for p in result.pois],
    }


def _trajectory(user_id: str) -> list[list[list[float]]]:
    """Clean GPS points thinned to at most MAX_TRAJECTORY_POINTS, one polyline per segment."""
    path = USER_DIR / f"user_{user_id}.parquet"
    if not path.exists():
        return []
    df = pd.read_parquet(path, columns=["datetime", "lat", "lon", "sub_trip_id"]).sort_values("datetime")
    df = df.iloc[:: max(1, len(df) // MAX_TRAJECTORY_POINTS)]
    return [seg[["lat", "lon"]].round(5).values.tolist()
            for _, seg in df.groupby("sub_trip_id", sort=False) if len(seg) >= 2]


def user_summary(user_id: str, v1: HeuristicClassifier, v2: ClusterClassifier, with_trajectory: bool) -> dict:
    stays = load_stays(user_id, v1.min_duration_minutes)
    r1, r2 = v1.predict(stays), v2.predict(stays)
    lats, lons = [sp.lat for sp in stays], [sp.lon for sp in stays]
    arrivals = local_times([sp.arrival_time for sp in stays], lats, lons)
    departures = local_times([sp.departure_time for sp in stays], lats, lons)
    labels = place_labels(lats, lons, v2.eps_meters, v2.min_samples)

    stay_rows = []
    for sp, arr, dep, label in zip(stays, arrivals, departures, labels, strict=True):
        home_min, office_min = v1.window_minutes(arr, dep)
        stay_rows.append({
            "lat": sp.lat, "lon": sp.lon, "place": int(label),
            "arrival_local": arr.isoformat(), "departure_local": dep.isoformat(),
            "duration_minutes": sp.duration_minutes, "observed_minutes": sp.observed_minutes,
            "home_minutes": home_min, "office_minutes": office_min,
        })

    places = []
    for label in sorted(set(labels.tolist())):
        members = [s for s in stay_rows if s["place"] == label]
        weights = [s["duration_minutes"] for s in members]
        lat = float(np.average([s["lat"] for s in members], weights=weights))
        lon = float(np.average([s["lon"] for s in members], weights=weights))
        places.append({
            "place": label, "lat": lat, "lon": lon, "stays": len(members),
            "radius_m": max(haversine_meters(lat, lon, s["lat"], s["lon"]) for s in members),
            "duration_minutes": sum(weights),
            "home_minutes": sum(s["home_minutes"] for s in members),
            "office_minutes": sum(s["office_minutes"] for s in members),
        })

    def place_of(loc) -> int | None:
        """v2 place whose duration-weighted centre is the v2 answer."""
        if loc is None:
            return None
        return min(places, key=lambda p: haversine_meters(p["lat"], p["lon"], loc.lat, loc.lon))["place"]

    home_place, office_place = place_of(r2.home), place_of(r2.office)
    profile = {}
    for name, label in (("home", home_place), ("office", office_place)):
        if label is not None:
            local = [(a, d) for a, d, lab in zip(arrivals, departures, labels, strict=True) if lab == label]
            profile[name] = _hourly_minutes(local, v1.work_days)

    return {
        "user_id": user_id,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "config": {
            "home_window": [v1.home_hour_start, v1.home_hour_end],
            "office_window": [v1.office_hour_start, v1.office_hour_end],
            "work_days": list(v1.work_days),
            "min_window_minutes": v1.min_window_minutes,
            "support_radius_m": v1.support_radius_m,
            "eps_meters": v2.eps_meters, "min_samples": v2.min_samples, "min_window_days": v2.min_window_days,
        },
        "v1": _result_dict(r1),
        "v2": _result_dict(r2),
        "v2_home_place": home_place,
        "v2_office_place": office_place,
        "stays": stay_rows,
        "places": places,
        "hourly_profile": profile,
        "trajectory": _trajectory(user_id) if with_trajectory else [],
    }


# ── Rendering ────────────────────────────────────────────────────────────────


def profile_png(summary: dict) -> str:
    """Hourly profile of the v2 home and office places as a base64 PNG."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    cfg = summary["config"]
    fig, axes = plt.subplots(1, 2, figsize=(8, 2.6), sharey=True)
    hours = np.arange(24)
    for ax, kind, title in zip(axes, ("workday", "other"), ("Mon-Fri", "Sat-Sun"), strict=True):
        h0, h1 = cfg["home_window"]
        ax.axvspan(h0, 24, color="#1f4e8c", alpha=0.08)
        ax.axvspan(0, h1, color="#1f4e8c", alpha=0.08)
        if kind == "workday":
            ax.axvspan(*cfg["office_window"], color="#e07b00", alpha=0.10)
        for name, color in (("home", "#1f4e8c"), ("office", "#e07b00")):
            if name in summary["hourly_profile"]:
                ax.step(hours, np.array(summary["hourly_profile"][name][kind]) / 60.0, where="post",
                        color=color, label=f"{name} place (v2)")
        ax.set_title(title, fontsize=9)
        ax.set_xticks(range(0, 25, 3))
        ax.set_xlim(0, 24)
        ax.set_xlabel("local hour", fontsize=8)
        ax.tick_params(labelsize=7)
    axes[0].set_ylabel("total hours", fontsize=8)
    axes[1].legend(fontsize=7, loc="upper right")
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110)
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def _status_text(status: dict) -> str:
    text = status["status"]
    if status["reason"]:
        text += f" ({status['reason']})"
    if status["window_minutes"] is not None:
        text += f", {status['window_minutes']:.0f} window min, support {status['support']}"
    return text


def _answer_popup(version: str, kind: str, loc: dict, status: dict) -> str:
    return (f"<b>{version} {kind}</b><br>{loc['lat']:.5f}, {loc['lon']:.5f}<br>"
            f"confidence {loc['confidence']:.2f}<br>{_status_text(status)}<br>"
            f"{loc['visit_count']} stay(s), {loc['duration_minutes'] / 60:.1f} h")


def render_map(summary: dict, out_path: Path) -> None:
    import folium

    v1, v2 = summary["v1"], summary["v2"]
    m = folium.Map(tiles=None, control_scale=True)
    for name, service in BASE_LAYERS.items():
        folium.TileLayer(ESRI_TILES.format(service), attr="Tiles &copy; Esri", name=name, max_zoom=19,
                         show=name == "streets").add_to(m)

    if summary["trajectory"]:
        layer = folium.FeatureGroup("GPS trajectory (thinned)", show=False)
        for seg in summary["trajectory"]:
            folium.PolyLine(seg, color="#888", weight=1, opacity=0.6).add_to(layer)
        layer.add_to(m)

    layer = folium.FeatureGroup("v2 places (DBSCAN)")
    for p in summary["places"]:
        if p["stays"] < 2:
            continue
        folium.Circle([p["lat"], p["lon"]], radius=max(p["radius_m"], 30.0), color="#6a3d9a", weight=1,
                      fill=True, fill_opacity=0.05,
                      tooltip=f"place {p['place']}: {p['stays']} stays, home {p['home_minutes']:.0f} min, "
                              f"office {p['office_minutes']:.0f} min").add_to(layer)
    layer.add_to(m)

    layer = folium.FeatureGroup("stay-points")
    for s in summary["stays"]:
        color = "#1f4e8c" if s["home_minutes"] >= s["office_minutes"] and s["home_minutes"] > 0 else (
            "#e07b00" if s["office_minutes"] > 0 else "#999")
        folium.CircleMarker(
            [s["lat"], s["lon"]], radius=3 + min(6.0, s["duration_minutes"] / 180.0), color=color, weight=1,
            fill=True, fill_opacity=0.6,
            popup=folium.Popup(
                f"<b>stay</b> (place {s['place']})<br>{s['arrival_local']} → {s['departure_local']} local<br>"
                f"{s['duration_minutes']:.0f} min, home {s['home_minutes']:.0f}, office {s['office_minutes']:.0f}",
                max_width=320)).add_to(layer)
    layer.add_to(m)

    layer = folium.FeatureGroup("v2 POIs")
    for i, p in enumerate(v2["pois"], 1):
        folium.Marker([p["lat"], p["lon"]], icon=folium.Icon(color="gray", icon="star", prefix="fa"),
                      tooltip=f"v2 POI {i}: {p['visit_count']} stays, {p['duration_minutes'] / 60:.1f} h").add_to(layer)
    layer.add_to(m)

    styles = {"home": ("home", "lightblue", "darkblue"), "office": ("briefcase", "beige", "orange")}
    for version, result, shade in (("v1", v1, 1), ("v2", v2, 2)):
        layer = folium.FeatureGroup(f"{version} home / office")
        for kind in ("home", "office"):
            loc = result[kind]
            if loc is None:
                continue
            icon, *colors = styles[kind]
            folium.Marker([loc["lat"], loc["lon"]], icon=folium.Icon(color=colors[shade - 1], icon=icon, prefix="fa"),
                          tooltip=f"{version} {kind}",
                          popup=folium.Popup(_answer_popup(version, kind, loc, result[f"{kind}_status"]),
                                             max_width=320)).add_to(layer)
            if version == "v1":
                folium.Circle([loc["lat"], loc["lon"]], radius=summary["config"]["support_radius_m"],
                              color=colors[1], weight=1, dash_array="4", fill=False).add_to(layer)
        layer.add_to(m)

    answers = [r[k] for r in (v1, v2) for k in ("home", "office") if r[k]]
    m.fit_bounds([[min(a["lat"] for a in answers), min(a["lon"] for a in answers)],
                  [max(a["lat"] for a in answers), max(a["lon"] for a in answers)]], padding=(80, 80))
    folium.LayerControl(collapsed=False).add_to(m)

    rows = "".join(
        f"<tr><td>{v}</td><td>{k}</td><td>{_status_text(r[f'{k}_status'])}</td>"
        f"<td>{r[k]['confidence']:.2f}</td></tr>" if r[k] else
        f"<tr><td>{v}</td><td>{k}</td><td>{_status_text(r[f'{k}_status'])}</td><td>-</td></tr>"
        for v, r in (("v1", v1), ("v2", v2)) for k in ("home", "office"))
    panel = f"""
    <div style="position:fixed;bottom:16px;left:16px;z-index:9999;background:white;padding:8px 10px;
                border-radius:6px;box-shadow:0 1px 6px rgba(0,0,0,.3);font:12px sans-serif;max-width:640px">
      <details open><summary><b>User {summary['user_id']}</b>: {len(summary['stays'])} stay-points,
        {sum(p['stays'] >= 2 for p in summary['places'])} v2 places</summary>
        <table style="border-collapse:collapse;margin:6px 0" cellpadding="3">
          <tr><th align=left>model</th><th align=left>type</th><th align=left>status</th><th>conf.</th></tr>{rows}
        </table>
        <div>Light markers / dashed 200 m circle = v1 (one stay); dark markers = v2 (DBSCAN place).
          Dots: blue = home-window minutes, orange = office-window minutes, grey = neither.</div>
        <img src="data:image/png;base64,{profile_png(summary)}" style="width:100%;margin-top:6px">
      </details>
    </div>"""
    m.get_root().html.add_child(folium.Element(panel))
    m.save(str(out_path))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--candidates", action="store_true", help="list users suitable for the map")
    group.add_argument("--user", help="user id, e.g. 068")
    parser.add_argument("--no-trajectory", action="store_true", help="leave the GPS trajectory layer out")
    args = parser.parse_args()

    v1, v2 = build_classifiers()
    if args.candidates:
        df = list_candidates(v1, v2)
        with pd.option_context("display.width", 200, "display.max_rows", 200, "display.float_format", "{:.2f}".format):
            print(df.to_string(index=False))
        print(f"\n{len(df)} users ({int(df.v1_equals_v2.sum())} with v1 = v2 within {SAME_PLACE_M:.0f} m)")
        return 0

    user_id = args.user.zfill(3)
    out_dir = REPORT_DIR / f"user_{user_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = user_summary(user_id, v1, v2, with_trajectory=not args.no_trajectory)
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False), encoding="utf-8")
    render_map(summary, out_dir / "map.html")
    print(f"wrote {out_dir / 'map.html'} and summary.json")
    for version in ("v1", "v2"):
        for kind in ("home", "office"):
            print(f"  {version} {kind}: {_status_text(summary[version][f'{kind}_status'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
