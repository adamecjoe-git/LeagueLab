"""LeagueLab preseason newsletter.

Usage:
    python -m leaguelab.preseason_newsletter --season 2026

The builder reads:
    data/config/<season>/preseason.json
    data/config/<season>/dues.json

preseason.json is intentionally data-driven.  Draft analytics can populate the
same schema after Yahoo draft/projection inspection without changing the HTML.
Python 3.8 compatible.
"""
import argparse
import json
import re
import statistics
from html import escape
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_ROOT = PROJECT_ROOT / "data" / "config"
OUTPUT_ROOT = PROJECT_ROOT / "output"
RAW_YAHOO_ROOT = PROJECT_ROOT / "data" / "raw" / "yahoo"


CHALLENGES = [
    ("Hot Start", "Weeks 1-2", 10, "Most total starting-lineup points across the two challenge weeks."),
    ("Dynamic Duo", "Weeks 3-4", 10, "Most combined points from each team's two highest-scoring starters each week."),
    ("Flex Appeal", "Weeks 5-6", 10, "Most points scored from the W/R/T flex positions across the two weeks."),
    ("Depth Charge", "Weeks 7-8", 10, "Most combined points from RB2, WR2, FLEX1 and FLEX2 across the two weeks."),
    ("Perfect Lineup", "Weeks 9-10", 10, "Highest lineup efficiency: actual starter points divided by the optimal legal lineup."),
    ("No Weak Links", "Weeks 11-12", 10, "Highest combined score from each team's lowest-scoring starter each week."),
    ("Finish Strong", "Weeks 13-14", 10, "Largest improvement over the team's expected two-week score based on its Weeks 1-12 average."),
    ("Season Points", "Weeks 1-14", 20, "Most total fantasy points scored during the 14-week regular season."),
]

DEFAULT_PAYOUTS = [
    ("1st Place", 210),
    ("2nd Place", 100),
    ("3rd Place", 40),
    ("Toilet Bowl", 40),
    ("Challenges", 90),
]


def _load_json(path, default=None):
    if not path.exists():
        return {} if default is None else default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _money(value):
    return "${:,.0f}".format(float(value or 0))


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _find_yahoo_league_dir(season):
    base = RAW_YAHOO_ROOT / str(season)
    candidates = [path for path in base.glob("*") if path.is_dir()]
    if len(candidates) != 1:
        raise RuntimeError(
            "Expected exactly one Yahoo league directory under {}, found {}.".format(
                base, len(candidates)
            )
        )
    return candidates[0]


def _recursive_first(value, key):
    if isinstance(value, dict):
        if key in value:
            return value.get(key)
        for child in value.values():
            found = _recursive_first(child, key)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _recursive_first(child, key)
            if found is not None:
                return found
    return None


def _collect_draft_results(value, output):
    if isinstance(value, dict):
        draft_result = value.get("draft_result")
        if isinstance(draft_result, dict) and draft_result.get("player_key"):
            output.append(draft_result)
        for child in value.values():
            _collect_draft_results(child, output)
    elif isinstance(value, list):
        for child in value:
            _collect_draft_results(child, output)


def _collect_player_analysis(value, output):
    """Extract player metadata + draft_analysis from Yahoo batch responses."""
    if isinstance(value, dict):
        player = value.get("player")
        if isinstance(player, list):
            player_key = _recursive_first(player, "player_key")
            analysis = _recursive_first(player, "draft_analysis")
            if player_key and analysis is not None:
                output[str(player_key)] = {
                    "player_key": str(player_key),
                    "player_name": _recursive_first(player, "full") or "",
                    "position": _recursive_first(player, "display_position") or "",
                    "average_pick": _to_float(_recursive_first(analysis, "average_pick")),
                    "average_round": _to_float(_recursive_first(analysis, "average_round")),
                    "percent_drafted": _to_float(_recursive_first(analysis, "percent_drafted")),
                    "preseason_average_pick": _to_float(_recursive_first(analysis, "preseason_average_pick")),
                    "preseason_average_round": _to_float(_recursive_first(analysis, "preseason_average_round")),
                    "preseason_percent_drafted": _to_float(_recursive_first(analysis, "preseason_percent_drafted")),
                }
        for child in value.values():
            _collect_player_analysis(child, output)
    elif isinstance(value, list):
        for child in value:
            _collect_player_analysis(child, output)


def _team_name_map(teams_payload):
    result = {}

    def walk(value):
        if isinstance(value, dict):
            team = value.get("team")
            if isinstance(team, list):
                team_key = _recursive_first(team, "team_key")
                team_name = _recursive_first(team, "name")
                if team_key and team_name:
                    result[str(team_key)] = str(team_name)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(teams_payload)
    return result


def build_draft_analysis_rows(season):
    """Join league draft picks to the frozen Yahoo ADP snapshot."""
    league_dir = _find_yahoo_league_dir(season)
    draft_payload = _load_json(league_dir / "draft_results.json", {})
    analysis_payload = _load_json(league_dir / "draft_analysis.json", {})
    teams_payload = _load_json(league_dir / "teams.json", {})

    picks = []
    _collect_draft_results(draft_payload, picks)
    picks.sort(key=lambda item: int(item.get("pick") or 999999))

    analysis_by_player = {}
    _collect_player_analysis(analysis_payload.get("batches", analysis_payload), analysis_by_player)
    team_names = _team_name_map(teams_payload)

    rows = []
    for pick in picks:
        player_key = str(pick.get("player_key") or "")
        info = analysis_by_player.get(player_key, {})
        actual_pick = int(pick.get("pick") or 0)
        average_pick = info.get("average_pick")
        draft_value = None
        if average_pick is not None and actual_pick:
            # Positive = selected later than Yahoo ADP (value).
            # Negative = selected earlier than Yahoo ADP (reach).
            draft_value = round(float(actual_pick) - float(average_pick), 1)

        team_key = str(pick.get("team_key") or "")
        rows.append({
            "pick": actual_pick,
            "round": int(pick.get("round") or 0),
            "team_key": team_key,
            "team_name": team_names.get(team_key, team_key),
            "player_key": player_key,
            "player_name": info.get("player_name", ""),
            "position": info.get("position", ""),
            "average_pick": average_pick,
            "average_round": info.get("average_round"),
            "percent_drafted": info.get("percent_drafted"),
            "preseason_average_pick": info.get("preseason_average_pick"),
            "preseason_average_round": info.get("preseason_average_round"),
            "preseason_percent_drafted": info.get("preseason_percent_drafted"),
            # Positive = selected later than Yahoo ADP (value).
            # Negative = selected earlier than Yahoo ADP (reach).
            "draft_value": draft_value,
        })

    return rows


def write_draft_analysis_report(season):
    rows = build_draft_analysis_rows(season)
    out_dir = OUTPUT_ROOT / str(season)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "draft_analysis.json"
    path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    return path, rows


def _section(title, body, subtitle=""):
    sub = '<div class="section-sub">{}</div>'.format(escape(subtitle)) if subtitle else ""
    return '<div class="section"><h2>{}</h2>{}{}</div>'.format(escape(title), sub, body)


def _table(headers, rows):
    head = "".join("<th>{}</th>".format(escape(str(h))) for h in headers)
    body = []
    for row in rows:
        body.append("<tr>{}</tr>".format("".join(
            "<td>{}</td>".format(value) for value in row
        )))
    return '<div class="table-wrap"><table><thead><tr>{}</tr></thead><tbody>{}</tbody></table></div>'.format(
        head, "".join(body)
    )


def _welcome(data, season):
    message = data.get("welcome_message") or (
        "Welcome back to XTreme Football. The draft is complete and another "
        "season is ready to go. Here is your preseason look at the league."
    )
    return _section(
        "🏈 Welcome to the {} Season".format(season),
        '<div class="welcome-copy">{}</div>'.format(escape(message)),
    )


def _payouts(data):
    configured = data.get("payouts") or {}
    rows = []
    total = 0
    for label, default in DEFAULT_PAYOUTS:
        key = label.lower().replace(" ", "_")
        amount = configured.get(key, default)
        total += float(amount)
        rows.append([escape(label), '<strong>{}</strong>'.format(_money(amount))])
    rows.append(['<strong>Total</strong>', '<strong>{}</strong>'.format(_money(total))])
    return _section("💰 Payout Structure", _table(["Award", "Payout"], rows))


def _challenges(data):
    overrides = data.get("challenges") or {}
    rows = []
    for name, weeks, prize, description in CHALLENGES:
        item = overrides.get(name, {}) if isinstance(overrides, dict) else {}
        rows.append([
            '<strong>{}</strong>'.format(escape(name)),
            escape(str(item.get("weeks", weeks))),
            '<strong>{}</strong>'.format(_money(item.get("prize", prize))),
            escape(str(item.get("description", description))),
        ])
    return _section(
        "🏆 Challenge Schedule",
        _table(["Challenge", "Weeks", "Payout", "Description"], rows),
        "$90 total challenge pool",
    )


def _dues(season):
    cfg = _load_json(CONFIG_ROOT / str(season) / "dues.json", {})
    amount = cfg.get("amount_per_team", 40)
    teams = cfg.get("teams") or {}
    rows = []
    if isinstance(teams, dict):
        team_items = list(teams.items())
    elif isinstance(teams, list):
        team_items = [(str(index + 1), item) for index, item in enumerate(teams)]
    else:
        team_items = []

    for key, item in team_items:
        if not isinstance(item, dict):
            continue
        name = item.get("team_name") or item.get("name") or key
        paid = bool(item.get("paid"))
        rows.append([
            escape(str(name)),
            _money(item.get("amount_paid", amount) if paid else amount),
            '<span class="paid">Paid</span>' if paid else '<span class="unpaid">Due</span>',
        ])
    if not rows:
        return _section(
            "💵 League Dues",
            '<div class="empty">Dues status will appear here once dues.json is populated.</div>',
            "{} per team".format(_money(amount)),
        )
    return _section("💵 League Dues", _table(["Team", "Dues", "Status"], rows), "{} per team".format(_money(amount)))



def _yahoo_draft_grades(season):
    """Return Yahoo draft grades keyed by team_key from captured teams.json."""
    try:
        league_dir = _find_yahoo_league_dir(season)
    except RuntimeError:
        return {}

    path = league_dir / "teams.json"
    if not path.exists():
        return {}

    payload = _load_json(path, {})
    grades = {}

    def walk(value):
        if isinstance(value, dict):
            team_key = value.get("team_key")
            grade = value.get("draft_grade")
            if team_key and grade:
                grades[str(team_key)] = str(grade)
            team_name = value.get("name")
            if team_name and grade:
                grades["name:" + str(team_name)] = str(grade)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            # Yahoo often stores team metadata as a list of one-key dicts.
            team_key = None
            team_name = None
            grade = None
            for child in value:
                if isinstance(child, dict):
                    if "team_key" in child:
                        team_key = child.get("team_key")
                    if "name" in child and team_name is None:
                        team_name = child.get("name")
                    if "draft_grade" in child:
                        grade = child.get("draft_grade")
            if team_key and grade:
                grades[str(team_key)] = str(grade)
            if team_name and grade:
                grades["name:" + str(team_name)] = str(grade)
            for child in value:
                walk(child)

    walk(payload)
    return grades



SKILL_POSITIONS = {"QB", "RB", "WR", "TE"}


def _is_skill_position(position):
    """Return True for offensive fantasy skill positions used in draft analysis.

    Yahoo may occasionally return compound display-position strings, so split
    on common separators and accept the row when any token is QB/RB/WR/TE.
    K and DEF/DST are intentionally excluded because their ADP deltas can
    overwhelm the much more meaningful skill-position draft values.
    """
    text = str(position or "").upper()
    for sep in ("/", ",", "|"):
        text = text.replace(sep, " ")
    tokens = {token.strip() for token in text.split() if token.strip()}
    return bool(tokens & SKILL_POSITIONS)


def _draft_extremes_by_team(season):
    """Return skill-position best-value and biggest-reach picks for each team.

    Yahoo ADP is a pick number, so a *larger* actual pick number means the
    player lasted longer than expected (value), while a *smaller* actual pick
    number means the player was taken earlier than expected (reach).

    Only QB/RB/WR/TE are considered.  K and DEF/DST are excluded because
    their draft-market ADP behaves differently and can distort the extremes.
    """
    try:
        rows = build_draft_analysis_rows(season)
    except (RuntimeError, OSError, ValueError, TypeError):
        return {}

    grouped = {}
    for row in rows:
        if not _is_skill_position(row.get("position")):
            continue

        team_key = str(row.get("team_key") or "")
        team_name = str(row.get("team_name") or "")
        actual = _to_float(row.get("pick"))
        adp = _to_float(row.get("average_pick"))
        if actual is None or adp is None:
            continue

        # Positive = value (taken later than ADP); negative = reach.
        delta = float(actual) - float(adp)
        entry = dict(row)
        entry["draft_value"] = round(delta, 1)

        for key in (team_key, "name:" + team_name if team_name else ""):
            if not key:
                continue
            bucket = grouped.setdefault(key, {"best_value": None, "biggest_reach": None})
            if delta > 0 and (bucket["best_value"] is None or delta > bucket["best_value"]["draft_value"]):
                bucket["best_value"] = entry
            if delta < 0 and (bucket["biggest_reach"] is None or delta < bucket["biggest_reach"]["draft_value"]):
                bucket["biggest_reach"] = entry

    return grouped


def _format_draft_extreme(row):
    if not row:
        return ""
    player = str(row.get("player_name") or "-")
    pick = int(float(row.get("pick") or 0))
    adp = float(row.get("average_pick") or 0)
    return "{} — #{} vs {:.1f} ADP".format(player, pick, adp)


# LeagueLab v1 draft-grading methodology.
#
# Draft value invariant:
#     actual pick - Yahoo ADP > 0  => VALUE (player lasted later than market)
#     actual pick - Yahoo ADP < 0  => REACH (player was taken earlier than market)
#
# ADP efficiency is calculated only from QB/RB/WR/TE, caps each individual
# pick's raw ADP delta at +/-24 picks, and discounts later rounds so a Round
# 13 flyer cannot erase an expensive early-round decision.
_DRAFT_VALUE_CAP = 24.0
_DRAFT_ROUND_WEIGHTS = {
    1: 1.00, 2: 1.00, 3: 1.00,
    4: 0.85, 5: 0.85, 6: 0.85,
    7: 0.65, 8: 0.65, 9: 0.65,
    10: 0.45, 11: 0.45, 12: 0.45,
    13: 0.25, 14: 0.25,
}
_DRAFT_ROSTER_WEIGHT = 0.60
_DRAFT_ADP_WEIGHT = 0.40


def _draft_round_weight(round_number):
    return _DRAFT_ROUND_WEIGHTS.get(int(round_number or 0), 0.25)


def _standardize(values):
    """Return z-scores keyed like *values*, with a zero-score safe fallback."""
    if not values:
        return {}
    nums = list(values.values())
    mean = statistics.mean(nums)
    sd = statistics.pstdev(nums)
    if not sd:
        return {key: 0.0 for key in values}
    return {key: (value - mean) / sd for key, value in values.items()}


def _draft_adp_efficiency(season):
    """Return LeagueLab v1 ADP-efficiency scores by team.

    The score is the round-weighted average of capped raw draft-value deltas.
    A positive score means the team generally selected players later than Yahoo
    ADP (value); a negative score means it generally selected them earlier
    than Yahoo ADP (reach).  K and DEF/DST are excluded.
    """
    try:
        rows = build_draft_analysis_rows(season)
    except (RuntimeError, OSError, ValueError, TypeError):
        return {}

    grouped = {}
    for row in rows:
        if not _is_skill_position(row.get("position")):
            continue
        actual = _to_float(row.get("pick"))
        adp = _to_float(row.get("average_pick"))
        round_number = int(row.get("round") or 0)
        if actual is None or adp is None or not round_number:
            continue

        # LOCKED convention: positive = value, negative = reach.
        raw_delta = float(actual) - float(adp)
        capped_delta = max(-_DRAFT_VALUE_CAP, min(_DRAFT_VALUE_CAP, raw_delta))
        weight = _draft_round_weight(round_number)
        team_key = str(row.get("team_key") or "")
        team_name = str(row.get("team_name") or "")

        for key in (team_key, "name:" + team_name if team_name else ""):
            if not key:
                continue
            bucket = grouped.setdefault(key, {"weighted_total": 0.0, "weight_total": 0.0})
            bucket["weighted_total"] += capped_delta * weight
            bucket["weight_total"] += weight

    scores = {}
    for key, bucket in grouped.items():
        if bucket["weight_total"]:
            scores[key] = bucket["weighted_total"] / bucket["weight_total"]
    return scores


def _draft_grade_from_composite(composite):
    """Map standardized LeagueLab composite score to a letter grade."""
    if composite >= 1.50:
        return "A+"
    if composite >= 1.00:
        return "A"
    if composite >= 0.50:
        return "A-"
    if composite >= 0.00:
        return "B+"
    if composite >= -0.50:
        return "B"
    if composite >= -1.00:
        return "B-"
    if composite >= -1.50:
        return "C+"
    return "C"


def _leaguelab_draft_grades(data, season):
    """Calculate LeagueLab v1 draft grades from roster quality + ADP value.

    Final Draft Grade = 60% finished-roster construction + 40% ADP efficiency.

    Roster construction uses the preseason LeagueLab Power Ranking already
    present in preseason.json.  Both components are standardized across the
    league before combining so the 60/40 weighting is meaningful.  If the raw
    Yahoo inputs or power rankings are unavailable, callers can safely fall
    back to the configured grade in preseason.json.
    """
    adp_by_key = _draft_adp_efficiency(season)
    power_rows = data.get("power_rankings") or []
    draft_rows = data.get("draft_report") or []
    if not adp_by_key or not power_rows or not draft_rows:
        return {}

    # Resolve each Draft Report team to a roster rank and an ADP-efficiency
    # score.  Higher roster_raw is better (12-team rank #1 -> 12, #12 -> 1).
    power_rank_by_name = {
        str(row.get("team_name") or ""): int(row.get("rank") or idx)
        for idx, row in enumerate(power_rows, 1)
        if row.get("team_name")
    }
    team_records = {}
    league_size = max(len(power_rows), 1)
    for team in draft_rows:
        team_name = str(team.get("team_name") or "")
        team_key = str(team.get("team_key") or "")
        roster_rank = power_rank_by_name.get(team_name)
        adp_score = adp_by_key.get(team_key, adp_by_key.get("name:" + team_name))
        if not team_name or roster_rank is None or adp_score is None:
            continue
        team_records[team_name] = {
            "team_key": team_key,
            "roster_rank": roster_rank,
            "roster_raw": (league_size + 1) - roster_rank,
            "adp_efficiency": adp_score,
        }

    # Do not partially calculate a league and silently distort z-scores.
    if len(team_records) != len(draft_rows):
        return {}

    roster_z = _standardize({name: r["roster_raw"] for name, r in team_records.items()})
    adp_z = _standardize({name: r["adp_efficiency"] for name, r in team_records.items()})

    results = {}
    for team_name, record in team_records.items():
        composite = (
            _DRAFT_ROSTER_WEIGHT * roster_z[team_name]
            + _DRAFT_ADP_WEIGHT * adp_z[team_name]
        )
        result = dict(record)
        result.update({
            "roster_z": roster_z[team_name],
            "adp_z": adp_z[team_name],
            "composite": composite,
            "grade": _draft_grade_from_composite(composite),
        })
        results[team_name] = result
        if record["team_key"]:
            results[record["team_key"]] = result
    return results


def _draft_report(data, season):
    teams = data.get("draft_report") or []
    if not teams:
        return _section(
            "📋 Draft Report",
            '<div class="empty">Draft analysis pending Yahoo draft-result and projection analysis.</div>',
        )
    yahoo_grades = _yahoo_draft_grades(season)
    draft_extremes = _draft_extremes_by_team(season)
    leaguelab_grades = _leaguelab_draft_grades(data, season)
    cards = []
    for team in teams:
        tags = []
        for label, key in (("Best Pick", "best_pick"), ("Best Value", "best_value"),
                           ("Biggest Reach", "biggest_reach"), ("Strength", "strength"),
                           ("Weakness", "weakness")):
            value = team.get(key)
            if key in ("best_value", "biggest_reach"):
                team_key = str(team.get("team_key", "") or "")
                team_name = str(team.get("team_name", "") or "")
                extremes = draft_extremes.get(team_key, draft_extremes.get("name:" + team_name, {}))
                calculated = _format_draft_extreme(extremes.get(key)) if extremes else ""
                if calculated:
                    value = calculated
            if value:
                tags.append('<div class="draft-fact"><span>{}</span>{}</div>'.format(
                    escape(label), escape(str(value))
                ))
        team_key = str(team.get("team_key", "") or "")
        team_name = str(team.get("team_name", "") or "")
        yahoo_grade = yahoo_grades.get(
            team_key, yahoo_grades.get("name:" + team_name, "-")
        )
        grade_record = leaguelab_grades.get(team_key, leaguelab_grades.get(team_name, {}))
        leaguelab_grade = grade_record.get("grade", team.get("grade", "-"))
        cards.append(
            '<div class="draft-card"><div class="draft-head"><strong>{}</strong>'
            '<div class="grade-pair"><span><small>LeagueLab</small>{}</span>'
            '<span><small>Yahoo</small>{}</span></div></div><div class="draft-facts">{}</div>'
            '<p>{}</p></div>'.format(
                escape(str(team.get("team_name", "-"))),
                escape(str(leaguelab_grade)),
                escape(yahoo_grade),
                "".join(tags),
                escape(str(team.get("assessment", ""))),
            )
        )
    return _section(
        "📋 Draft Report",
        '<div class="draft-grid">{}</div>'.format("".join(cards)),
        "LeagueLab grades evaluate draft-day value versus frozen Yahoo ADP plus roster construction. Yahoo grades are Yahoo's own draft grades captured after the draft. Neither is the preseason Power Ranking.",
    )


def _projected_standings(data):
    rows = data.get("projected_standings") or []
    if not rows:
        return _section(
            "📊 Yahoo Week 1 Projection Check",
            '<div class="empty">Yahoo Week 1 team projections are not available yet.</div>',
            "Current Yahoo team projections; lineups and projections may still change before kickoff.",
        )
    table_rows = []
    for idx, row in enumerate(rows, 1):
        table_rows.append([
            str(row.get("rank", idx)),
            escape(str(row.get("team_name", "-"))),
            "{:.2f}".format(float(row.get("projected_points", 0))),
            escape(str(row.get("strength", ""))),
        ])
    return _section(
        "📊 Yahoo Week 1 Projection Check",
        _table(["Rank", "Team", "Week 1 Proj.", "Note"], table_rows),
        "A secondary reference only — current Yahoo lineups and projections may still change before kickoff.",
    )

_WATCH_ADP_LABELS = {
    "draft steal",
    "early-round value",
    "aggressive pick",
    "value + upside",
}


def _watch_candidate_rows(season):
    """Return drafted skill players with a usable Yahoo ADP and ADP delta.

    Delta uses the same convention as the Draft Report:
      actual pick - Yahoo ADP > 0  => drafted later than ADP => value
      actual pick - Yahoo ADP < 0  => drafted earlier than ADP => reach
    """
    try:
        rows = build_draft_analysis_rows(season)
    except (RuntimeError, OSError, ValueError, TypeError):
        return []

    candidates = []
    for row in rows:
        if not _is_skill_position(row.get("position")):
            continue
        pick = _to_float(row.get("pick"))
        adp = _to_float(row.get("average_pick"))
        if pick is None or adp is None:
            continue
        candidate = dict(row)
        candidate["draft_value"] = round(float(pick) - float(adp), 1)
        candidates.append(candidate)
    return candidates


def _watch_item_from_row(label, row):
    """Build one Players-to-Watch card from a draft-analysis row."""
    pick = int(float(row.get("pick") or 0))
    adp = float(row.get("average_pick") or 0)
    delta = float(row.get("draft_value") or 0)
    team = str(row.get("team_name") or "")

    if delta > 0:
        comparison = "{:.1f} picks later than Yahoo ADP".format(abs(delta))
    else:
        comparison = "{:.1f} picks earlier than Yahoo ADP".format(abs(delta))

    return {
        "label": label,
        "player_name": str(row.get("player_name") or "-"),
        "detail": "{} — Pick {} vs Yahoo ADP {:.1f} ({}).".format(
            team, pick, adp, comparison
        ),
    }


def _calculated_players_to_watch(data, season):
    """Preserve the six editorial tiles while selecting ADP cards correctly.

    The four ADP-driven categories are recalculated from the frozen Yahoo ADP
    snapshot.  Roster Anchor and Backfield to Watch remain editorial/configured.

    Selection rules:
      * Early-Round Value: best positive delta among picks 1-72.
      * Draft Steal: best remaining positive delta overall.
      * Value + Upside: next-best remaining positive delta.
      * Aggressive Pick: most negative delta (largest reach).

    Positive delta means actual pick > ADP (player lasted longer than expected).
    Negative delta means actual pick < ADP (player was taken earlier than expected).
    """
    items = data.get("players_to_watch") or []
    if not items:
        return []

    candidates = _watch_candidate_rows(season)
    if not candidates:
        return list(items)

    values = sorted(
        (row for row in candidates if row["draft_value"] > 0),
        key=lambda row: row["draft_value"],
        reverse=True,
    )
    reaches = sorted(
        (row for row in candidates if row["draft_value"] < 0),
        key=lambda row: row["draft_value"],
    )

    selected = {}
    used_players = set()

    early_values = [row for row in values if float(row.get("pick") or 999) <= 72]
    if early_values:
        selected["early-round value"] = early_values[0]
        used_players.add(str(early_values[0].get("player_key") or early_values[0].get("player_name")))

    remaining_values = [
        row for row in values
        if str(row.get("player_key") or row.get("player_name")) not in used_players
    ]
    if remaining_values:
        selected["draft steal"] = remaining_values[0]
        used_players.add(str(remaining_values[0].get("player_key") or remaining_values[0].get("player_name")))

    remaining_values = [
        row for row in values
        if str(row.get("player_key") or row.get("player_name")) not in used_players
    ]
    if remaining_values:
        selected["value + upside"] = remaining_values[0]

    if reaches:
        selected["aggressive pick"] = reaches[0]

    output = []
    for item in items:
        label = str(item.get("label", "Player to Watch") or "Player to Watch")
        key = label.strip().lower()
        row = selected.get(key)
        if key in _WATCH_ADP_LABELS and row:
            output.append(_watch_item_from_row(label, row))
        else:
            output.append(dict(item))
    return output


def _players_to_watch(data, season):
    items = _calculated_players_to_watch(data, season)
    if not items:
        return _section("⭐ Players to Watch", '<div class="empty">Players to watch will be selected from the completed draft analysis.</div>')
    cards = []
    for item in items:
        cards.append(
            '<div class="mini-card"><div class="mini-label">{}</div><strong>{}</strong>'
            '<div class="mini-detail">{}</div></div>'.format(
                escape(str(item.get("label", "Player to Watch"))),
                escape(str(item.get("player_name", "-"))),
                escape(str(item.get("detail", ""))),
            )
        )
    return _section("⭐ Players to Watch", '<div class="mini-grid">{}</div>'.format("".join(cards)))


def _power_rankings(data):
    rows = data.get("power_rankings") or []
    if not rows:
        return _section("🔮 Preseason Power Rankings", '<div class="empty">Preseason rankings pending draft and projection analysis.</div>')
    table_rows = []
    for idx, row in enumerate(rows, 1):
        table_rows.append([
            str(row.get("rank", idx)),
            escape(str(row.get("team_name", "-"))),
            escape(str(row.get("rating", ""))),
            escape(str(row.get("note", ""))),
        ])
    return _section(
        "🔮 Preseason Power Rankings",
        _table(["Rank", "Team", "Roster Read", "Outlook"], table_rows),
        "Finished-roster strength and depth; Yahoo Week 1 projections are used only as a secondary reference.",
    )


def _notifications():
    body = """
    <div class="notification-card">
      <p><strong>LeagueLab can send lineup alerts before your players' games begin.</strong> Alerts are available by <strong>text message, email, or both</strong> and are only sent when a potential lineup issue is detected, such as an empty starting position, a player on bye, or a player listed as unavailable.</p>
      <p><strong>Notifications are opt-in.</strong> If you'd like to receive them, reply to this email with <strong>TEXT</strong>, <strong>EMAIL</strong>, or <strong>BOTH</strong>.</p>
      <p>If choosing text, include the phone number you'd like to use. If choosing email, I'll use the email address you reply from unless you specify another one.</p>
      <p class="notification-note">You can opt out at any time.</p>
    </div>
    """
    return _section("📱 LeagueLab Notifications", body)


def _week_one(data):
    matchups = data.get("week_1_matchups") or []
    if not matchups:
        return _section("⚔️ Week 1 Matchups", '<div class="empty">Week 1 matchup projections pending Yahoo schedule/projection data.</div>')
    cards = []
    for item in matchups:
        a = item.get("team_a") or {}
        b = item.get("team_b") or {}
        watch = '<div class="watch">MATCHUP TO WATCH</div>' if item.get("matchup_to_watch") else ""
        def team_line(team):
            proj = team.get("projected_points")
            proj_html = ' <span class="projection">• Proj {:.2f}</span>'.format(float(proj)) if proj is not None else ""
            return '<strong>{}</strong>{}'.format(escape(str(team.get("team_name", "-"))), proj_html)
        cards.append('<div class="upcoming">{}<div>{}</div><div class="versus">vs</div><div>{}</div></div>'.format(
            watch, team_line(a), team_line(b)
        ))
    return _section("⚔️ Week 1 Matchups", '<div class="upcoming-grid">{}</div>'.format("".join(cards)))


def build_preseason_html(season):
    data = _load_json(CONFIG_ROOT / str(season) / "preseason.json", {})
    league_name = data.get("league_name", "XTreme Football")

    css = """
    *{box-sizing:border-box}body{margin:0;background:#edf4f8;color:#263746;font-family:Arial,Helvetica,sans-serif}
    .shell{max-width:920px;margin:0 auto;background:#fbfdff}.hero{padding:30px 28px;background:#567b95;color:#fff}
    .hero h1{margin:0;font-size:28px}.hero p{margin:7px 0 0;opacity:.9}.section{padding:22px 28px;border-bottom:1px solid #dce8ef}
    .section h2{margin:0 0 12px;color:#34576e;font-size:19px}.section-sub{margin:-7px 0 12px;color:#718694;font-size:11px}
    .welcome-copy{font-size:14px;line-height:1.55}.table-wrap{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:12px}
    th{text-align:left;background:#eaf3f8;padding:9px 8px;border-bottom:2px solid #bfd3df;white-space:nowrap}
    td{padding:9px 8px;border-bottom:1px solid #e1ebf0;vertical-align:top}.paid{font-weight:bold;color:#456b83}.unpaid{font-weight:bold}
    .draft-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}.draft-card{padding:14px;background:#f4f9fc;border:1px solid #d3e3ed;border-radius:9px}
    .draft-head{display:flex;justify-content:space-between;align-items:center;font-size:15px}.grade-pair{display:flex;gap:14px;text-align:center;color:#567b95}.grade-pair span{font-size:22px;font-weight:bold;line-height:1}.grade-pair small{display:block;margin-bottom:4px;color:#718694;font-size:8px;text-transform:uppercase;letter-spacing:.5px}
    .draft-facts{margin-top:8px}.draft-fact{margin-top:5px;font-size:11px}.draft-fact span{display:inline-block;width:84px;color:#718694;text-transform:uppercase;font-size:9px;font-weight:bold}
    .draft-card p{margin:10px 0 0;font-size:12px;line-height:1.45;color:#526b7b}.mini-grid,.upcoming-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
    .mini-card,.upcoming{padding:13px;background:#f0f7fb;border:1px solid #d1e1ea;border-radius:8px}.mini-label,.watch{font-size:9px;text-transform:uppercase;letter-spacing:.6px;color:#6f98b3;font-weight:bold}
    .mini-detail{margin-top:5px;font-size:11px;color:#6c8190}.versus{margin:6px 0;color:#8a9ba6;font-size:10px;text-transform:uppercase}
    .projection{color:#6f98b3;font-size:10px}.notification-card{padding:14px 16px;background:#f0f7fb;border:1px solid #d1e1ea;border-radius:8px;font-size:12px;line-height:1.5}.notification-card p{margin:0 0 9px}.notification-card p:last-child{margin-bottom:0}.notification-note{color:#718694;font-size:11px}.empty{padding:14px;background:#f7fbfd;border:1px dashed #c8d8e2;border-radius:8px;color:#7b909e;font-size:12px}
    .footer{padding:20px 28px;text-align:center;color:#8a9ba6;font-size:10px}
    @media(max-width:650px){.hero,.section{padding-left:16px;padding-right:16px}.draft-grid,.mini-grid,.upcoming-grid{grid-template-columns:1fr}table{font-size:11px}}
    """

    parts = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        "<title>{} Preseason Newsletter</title><style>{}</style></head><body>".format(season, css),
        '<div class="shell">',
        '<div class="hero"><h1>{} Preseason Newsletter</h1><p>LeagueLab • {} • Draft complete. Season loading.</p></div>'.format(
            escape(str(league_name)), season
        ),
        _welcome(data, season),
        _notifications(),
        _payouts(data),
        _challenges(data),
        _dues(season),
        _draft_report(data, season),
        _projected_standings(data),
        _players_to_watch(data, season),
        _power_rankings(data),
        _week_one(data),
        '<div class="footer">Generated by LeagueLab</div></div></body></html>',
    ]
    return "".join(parts)




def _email_escape(value):
    """Escape HTML and encode non-ASCII characters as numeric entities.

    Keeping the email body ASCII-only avoids Windows PowerShell/Outlook
    mojibake while preserving icons, smart punctuation, and player names.
    """
    text = escape(str(value if value is not None else ""))
    return text.encode("ascii", "xmlcharrefreplace").decode("ascii")


def _email_section(title, body, subtitle=""):
    subtitle_html = ""
    if subtitle:
        subtitle_html = (
            '<div style="margin:0 0 12px 0;color:#718694;font-size:12px;line-height:17px;">{}</div>'
        ).format(_email_escape(subtitle))
    return (
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
        'style="width:100%;border-collapse:collapse;background:#fbfdff;">'
        '<tr><td align="left" style="padding:22px 28px;border-bottom:1px solid #dce8ef;'
        'font-family:Arial,Helvetica,sans-serif;color:#263746;text-align:left;">'
        '<div style="margin:0 0 12px 0;color:#34576e;font-size:19px;font-weight:bold;line-height:24px;">{}</div>'
        '{}{}</td></tr></table>'
    ).format(_email_escape(title), subtitle_html, body)


def _email_table(headers, rows, widths=None):
    headers_html = []
    for idx, header in enumerate(headers):
        width_attr = ''
        if widths and idx < len(widths) and widths[idx]:
            width_attr = ' width="{}"'.format(widths[idx])
        headers_html.append(
            '<th{} align="left" style="padding:9px 8px;background:#eaf3f8;border-bottom:2px solid #bfd3df;'
            'font-family:Arial,Helvetica,sans-serif;font-size:12px;line-height:16px;color:#34576e;text-align:left;">{}</th>'.format(
                width_attr, _email_escape(header)
            )
        )
    body_html = []
    for row in rows:
        cells = []
        for idx, value in enumerate(row):
            width_attr = ''
            if widths and idx < len(widths) and widths[idx]:
                width_attr = ' width="{}"'.format(widths[idx])
            cells.append(
                '<td{} align="left" valign="top" style="padding:9px 8px;border-bottom:1px solid #e1ebf0;'
                'font-family:Arial,Helvetica,sans-serif;font-size:12px;line-height:16px;color:#263746;text-align:left;">{}</td>'.format(
                    width_attr, value
                )
            )
        body_html.append('<tr>{}</tr>'.format(''.join(cells)))
    return (
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
        'style="width:100%;border-collapse:collapse;table-layout:fixed;">'
        '<thead><tr>{}</tr></thead><tbody>{}</tbody></table>'
    ).format(''.join(headers_html), ''.join(body_html))


def _email_welcome(data, season):
    message = data.get("welcome_message") or (
        "Welcome back to XTreme Football. The draft is complete and another "
        "season is ready to go. Here is your preseason look at the league."
    )
    body = (
        '<div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:23px;'
        'color:#263746;text-align:left;">{}</div>'
        '<div style="margin-top:12px;font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:23px;'
        'color:#263746;text-align:left;"><strong>This is the first issue of the weekly league newsletter.</strong> '
        'Unless you tell me otherwise, it will be sent to your X-ES email account. '
        'You can also opt out if you prefer.</div>'
    ).format(_email_escape(message))
    return _email_section("🏈 Welcome to the {} Season".format(season), body)


def _email_notifications():
    body = (
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
        'style="width:100%;border-collapse:collapse;background:#f0f7fb;border:1px solid #d1e1ea;">'
        '<tr><td align="left" style="padding:14px 16px;font-family:Arial,Helvetica,sans-serif;'
        'font-size:12px;line-height:19px;color:#263746;text-align:left;">'
        '<p style="margin:0 0 9px 0;"><strong>LeagueLab can send lineup alerts before your players&#39; games begin.</strong> '
        'Alerts are available by <strong>text message, email, or both</strong> and are only sent when a potential lineup issue is detected, '
        'such as an empty starting position, a player on bye, or a player listed as unavailable.</p>'
        '<p style="margin:0 0 9px 0;"><strong>Notifications are opt-in.</strong> If you&#39;d like to receive them, reply to this email with '
        '<strong>TEXT</strong>, <strong>EMAIL</strong>, or <strong>BOTH</strong>.</p>'
        '<p style="margin:0 0 9px 0;">If choosing text, include the phone number you&#39;d like to use. If choosing email, I&#39;ll use the '
        'email address you reply from unless you specify another one.</p>'
        '<p style="margin:0;color:#718694;font-size:11px;">You can opt out at any time.</p>'
        '</td></tr></table>'
    )
    return _email_section("📱 LeagueLab Notifications", body)


def _email_payouts(data):
    configured = data.get("payouts") or {}
    rows = []
    total = 0
    for label, default in DEFAULT_PAYOUTS:
        key = label.lower().replace(" ", "_")
        amount = configured.get(key, default)
        total += float(amount)
        rows.append([_email_escape(label), '<strong>{}</strong>'.format(_email_escape(_money(amount)))])
    rows.append(['<strong>Total</strong>', '<strong>{}</strong>'.format(_email_escape(_money(total)))])
    return _email_section("💰 Payout Structure", _email_table(["Award", "Payout"], rows, ["72%", "28%"]))


def _email_challenges(data):
    overrides = data.get("challenges") or {}
    rows = []
    for name, weeks, prize, description in CHALLENGES:
        item = overrides.get(name, {}) if isinstance(overrides, dict) else {}
        rows.append([
            '<strong>{}</strong>'.format(_email_escape(name)),
            _email_escape(item.get("weeks", weeks)),
            '<strong>{}</strong>'.format(_email_escape(_money(item.get("prize", prize)))),
            _email_escape(item.get("description", description)),
        ])
    return _email_section(
        "🏆 Challenge Schedule",
        _email_table(["Challenge", "Weeks", "Payout", "Description"], rows, ["19%", "13%", "12%", "56%"]),
        "$90 total challenge pool",
    )


def _email_dues(season):
    cfg = _load_json(CONFIG_ROOT / str(season) / "dues.json", {})
    amount = cfg.get("amount_per_team", 40)
    teams = cfg.get("teams") or {}
    if isinstance(teams, dict):
        team_items = list(teams.items())
    elif isinstance(teams, list):
        team_items = [(str(index + 1), item) for index, item in enumerate(teams)]
    else:
        team_items = []
    rows = []
    for key, item in team_items:
        if not isinstance(item, dict):
            continue
        name = item.get("team_name") or item.get("name") or key
        paid = bool(item.get("paid"))
        rows.append([
            _email_escape(name),
            _email_escape(_money(item.get("amount_paid", amount) if paid else amount)),
            '<strong style="color:#456b83;">Paid</strong>' if paid else '<strong>Due</strong>',
        ])
    if not rows:
        body = (
            '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
            'style="background:#f7fbfd;border:1px dashed #c8d8e2;"><tr><td align="left" '
            'style="padding:14px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#7b909e;">'
            'Dues status will appear here once dues.json is populated.</td></tr></table>'
        )
    else:
        body = _email_table(["Team", "Dues", "Status"], rows, ["60%", "20%", "20%"])
    return _email_section("💵 League Dues", body, "{} per team".format(_money(amount)))


def _email_card_table(cards, columns=2):
    """Fixed-column Outlook-safe card layout."""
    rows = []
    cell_width = int(100 / columns)
    for index in range(0, len(cards), columns):
        chunk = cards[index:index + columns]
        cells = []
        for card in chunk:
            cells.append(
                '<td width="{}%" valign="top" style="width:{}%;padding:6px;text-align:left;">{}</td>'.format(
                    cell_width, cell_width, card
                )
            )
        while len(cells) < columns:
            cells.append('<td width="{}%" style="width:{}%;padding:6px;">&nbsp;</td>'.format(cell_width, cell_width))
        rows.append('<tr>{}</tr>'.format(''.join(cells)))
    return (
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
        'style="width:100%;border-collapse:collapse;table-layout:fixed;">{}</table>'
    ).format(''.join(rows))


def _email_clean_fact_value(value, label):
    """Remove accidental Markdown/duplicate labels from draft fact values."""
    text = str(value or "").strip()
    prefixes = [
        "**{}**".format(label),
        "**{}:**".format(label),
        "{}:".format(label),
        label,
    ]
    lower = text.lower()
    for prefix in prefixes:
        if lower.startswith(prefix.lower()):
            text = text[len(prefix):].lstrip(" :-")
            break
    return text


def _email_draft_report(data, season):
    teams = data.get("draft_report") or []
    if not teams:
        return _email_section("📋 Draft Report", "Draft analysis pending.")
    yahoo_grades = _yahoo_draft_grades(season)
    draft_extremes = _draft_extremes_by_team(season)
    leaguelab_grades = _leaguelab_draft_grades(data, season)
    cards = []
    for team in teams:
        fact_rows = []
        for label, key in (("Best Pick", "best_pick"), ("Best Value", "best_value"),
                           ("Biggest Reach", "biggest_reach"), ("Strength", "strength"),
                           ("Weakness", "weakness")):
            value = team.get(key)
            if key in ("best_value", "biggest_reach"):
                team_key = str(team.get("team_key", "") or "")
                team_name = str(team.get("team_name", "") or "")
                extremes = draft_extremes.get(team_key, draft_extremes.get("name:" + team_name, {}))
                calculated = _format_draft_extreme(extremes.get(key)) if extremes else ""
                if calculated:
                    value = calculated
            if value:
                clean_value = _email_clean_fact_value(value, label)
                fact_rows.append(
                    '<tr><td width="92" valign="top" style="width:92px;padding:3px 10px 3px 0;'
                    'font-family:Arial,Helvetica,sans-serif;color:#718694;text-transform:uppercase;'
                    'font-size:9px;font-weight:bold;line-height:14px;white-space:nowrap;">{}</td>'
                    '<td valign="top" style="padding:3px 0;font-family:Arial,Helvetica,sans-serif;'
                    'font-size:12px;line-height:16px;color:#263746;text-align:left;">{}</td></tr>'.format(
                        _email_escape(label), _email_escape(clean_value)
                    )
                )
        team_key = str(team.get("team_key", "") or "")
        team_name = str(team.get("team_name", "") or "")
        yahoo_grade = yahoo_grades.get(team_key, yahoo_grades.get("name:" + team_name, "-"))
        grade_record = leaguelab_grades.get(team_key, leaguelab_grades.get(team_name, {}))
        leaguelab_grade = grade_record.get("grade", team.get("grade", "-"))
        card = (
            '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
            'style="width:100%;border-collapse:collapse;background:#f4f9fc;border:1px solid #d3e3ed;">'
            '<tr><td height="270" valign="top" style="height:270px;padding:13px;">'
            '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"><tr>'
            '<td valign="top" align="left" style="padding:0;border:0;font-family:Arial,Helvetica,sans-serif;'
            'font-size:15px;line-height:19px;color:#263746;text-align:left;"><strong>{}</strong></td>'
            '<td width="130" align="right" valign="top" style="width:130px;padding:0;border:0;">'
            '<table role="presentation" cellspacing="0" cellpadding="0" border="0" align="right"><tr>'
            '<td align="center" style="padding:0 8px;color:#567b95;font-family:Arial,Helvetica,sans-serif;text-align:center;">'
            '<div style="font-size:8px;line-height:11px;color:#718694;text-transform:uppercase;">LeagueLab</div>'
            '<div style="font-size:22px;line-height:24px;font-weight:bold;">{}</div></td>'
            '<td align="center" style="padding:0 0 0 8px;color:#567b95;font-family:Arial,Helvetica,sans-serif;text-align:center;">'
            '<div style="font-size:8px;line-height:11px;color:#718694;text-transform:uppercase;">Yahoo</div>'
            '<div style="font-size:22px;line-height:24px;font-weight:bold;">{}</div></td>'
            '</tr></table></td></tr></table>'
            '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
            'style="margin-top:8px;border-collapse:collapse;">{}</table>'
            '<div style="margin-top:10px;font-family:Arial,Helvetica,sans-serif;font-size:13px;line-height:19px;color:#526b7b;text-align:left;">{}</div>'
            '</td></tr></table>'
        ).format(
            _email_escape(team_name),
            _email_escape(leaguelab_grade),
            _email_escape(yahoo_grade),
            ''.join(fact_rows),
            _email_escape(team.get("assessment", "")),
        )
        cards.append(card)
    return _email_section(
        "📋 Draft Report",
        _email_card_table(cards, 2),
        "LeagueLab grades evaluate draft-day value versus frozen Yahoo ADP plus roster construction. Yahoo grades are Yahoo's own draft grades captured after the draft. Neither is the preseason Power Ranking.",
    )


def _email_projected_standings(data):
    rows = data.get("projected_standings") or []
    if not rows:
        return _email_section(
            "📊 Yahoo Week 1 Projection Check",
            '<div style="padding:14px;background:#f7fbfd;border:1px dashed #c8d8e2;color:#7b909e;font-size:12px;">Yahoo Week 1 team projections are not available yet.</div>',
            "Current Yahoo team projections; lineups and projections may still change before kickoff.",
        )
    table_rows = []
    for idx, row in enumerate(rows, 1):
        table_rows.append([
            _email_escape(row.get("rank", idx)),
            _email_escape(row.get("team_name", "-")),
            _email_escape("{:.2f}".format(float(row.get("projected_points", 0)))),
            _email_escape(row.get("strength", "")),
        ])
    return _email_section(
        "📊 Yahoo Week 1 Projection Check",
        _email_table(["Rank", "Team", "Week 1 Proj.", "Note"], table_rows, ["9%", "38%", "18%", "35%"]),
        "A secondary reference only — current Yahoo lineups and projections may still change before kickoff.",
    )


def _email_players_to_watch(data, season):
    items = _calculated_players_to_watch(data, season)
    if not items:
        return _email_section("⭐ Players to Watch", "Players to watch will be selected from the completed draft analysis.")
    cards = []
    for item in items:
        cards.append(
            '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
            'style="width:100%;background:#f0f7fb;border:1px solid #d1e1ea;"><tr><td align="left" '
            'style="padding:13px;font-family:Arial,Helvetica,sans-serif;text-align:left;">'
            '<div style="font-size:9px;line-height:12px;text-transform:uppercase;color:#6f98b3;font-weight:bold;">{}</div>'
            '<div style="margin-top:3px;font-size:12px;line-height:16px;color:#263746;"><strong>{}</strong></div>'
            '<div style="margin-top:5px;font-size:11px;line-height:15px;color:#6c8190;">{}</div>'
            '</td></tr></table>'.format(
                _email_escape(item.get("label", "Player to Watch")),
                _email_escape(item.get("player_name", "-")),
                _email_escape(item.get("detail", "")),
            )
        )
    return _email_section("⭐ Players to Watch", _email_card_table(cards, 3))


def _email_power_rankings(data):
    rows = data.get("power_rankings") or []
    if not rows:
        return _email_section("🔮 Preseason Power Rankings", "Preseason rankings pending draft and projection analysis.")
    table_rows = []
    for idx, row in enumerate(rows, 1):
        table_rows.append([
            _email_escape(row.get("rank", idx)),
            _email_escape(row.get("team_name", "-")),
            _email_escape(row.get("rating", "")),
            _email_escape(row.get("note", "")),
        ])
    return _email_section(
        "🔮 Preseason Power Rankings",
        _email_table(["Rank", "Team", "Roster Read", "Outlook"], table_rows, ["9%", "38%", "20%", "33%"]),
        "Finished-roster strength and depth; Yahoo Week 1 projections are used only as a secondary reference.",
    )


def _email_week_one(data):
    matchups = data.get("week_1_matchups") or []
    if not matchups:
        return _email_section("⚔️ Week 1 Matchups", "Week 1 matchup projections pending Yahoo schedule/projection data.")

    # Match the regular-season newsletter presentation: featured matchup first,
    # two roomy columns, Power Ranking before each team, and a compact watch badge.
    matchups = sorted(matchups, key=lambda item: 0 if item.get("matchup_to_watch") else 1)
    power_rows = data.get("power_rankings") or []
    power_by_name = {str(row.get("team_name", "")): row.get("rank", idx)
                     for idx, row in enumerate(power_rows, 1)}

    cards = []
    for item in matchups:
        a = item.get("team_a") or {}
        b = item.get("team_b") or {}

        def team_line(team):
            name = str(team.get("team_name", "-") or "-")
            rank = power_by_name.get(name)
            prefix = '<strong>#{}&nbsp;</strong>'.format(_email_escape(rank)) if rank else ''
            proj = team.get("projected_points")
            projection = ''
            if proj is not None:
                projection = (' <span style="color:#6f98b3;font-size:11px;white-space:nowrap;">'
                              '&#8226;&nbsp;Proj&nbsp;{:.2f}</span>').format(float(proj))
            return '{}<strong>{}</strong>{}'.format(prefix, _email_escape(name), projection)

        badge = ''
        if item.get("matchup_to_watch"):
            badge = (
                '<td width="112" align="right" valign="top" style="width:112px;padding:0;border:0;">'
                '<span style="display:inline-block;padding:3px 6px;background:#dceef7;color:#4f7f9d;'
                'font-family:Arial,Helvetica,sans-serif;font-size:8px;line-height:10px;font-weight:bold;'
                'text-transform:uppercase;white-space:nowrap;">MATCHUP TO WATCH</span></td>'
            )

        first_line = team_line(a)
        if badge:
            top = (
                '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
                'style="width:100%;border-collapse:collapse;"><tr>'
                '<td valign="top" style="padding:0;border:0;font-family:Arial,Helvetica,sans-serif;'
                'font-size:13px;line-height:18px;color:#263746;text-align:left;">{}</td>{}</tr></table>'
            ).format(first_line, badge)
        else:
            top = '<div style="font-size:13px;line-height:18px;color:#263746;">{}</div>'.format(first_line)

        cards.append(
            '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
            'style="width:100%;background:#f0f7fb;border:1px solid #d1e1ea;border-collapse:collapse;">'
            '<tr><td valign="top" align="left" style="padding:11px 13px;font-family:Arial,Helvetica,sans-serif;'
            'font-size:13px;line-height:18px;color:#263746;text-align:left;">'
            '{}<div style="margin:2px 0;color:#8a9ba6;font-size:11px;line-height:15px;">vs</div>'
            '<div style="font-size:13px;line-height:18px;color:#263746;">{}</div>'
            '</td></tr></table>'.format(top, team_line(b))
        )

    return _email_section(
        "⚔️ Week 1 Matchups",
        _email_card_table(cards, 2),
        "Week 1 • Rank shown in LeagueLab Power Ranking",
    )


def build_preseason_email_html(season):
    """Build a fixed-width Outlook-friendly email without changing the browser version."""
    data = _load_json(CONFIG_ROOT / str(season) / "preseason.json", {})
    league_name = data.get("league_name", "XTreme Football")
    content = ''.join([
        _email_welcome(data, season),
        _email_notifications(),
        _email_payouts(data),
        _email_challenges(data),
        _email_dues(season),
        _email_draft_report(data, season),
        _email_projected_standings(data),
        _email_players_to_watch(data, season),
        _email_power_rankings(data),
        _email_week_one(data),
    ])
    # Fixed 900px canvas gives the three-column draft cards and two-column matchup
    # cards enough room while still preventing desktop Outlook from reflowing them.
    return (
        '<!doctype html><html><head><meta http-equiv="Content-Type" content="text/html; charset=utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1"><title>{} Preseason Newsletter</title></head>'
        '<body style="margin:0;padding:0;background:#edf4f8;">'
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" bgcolor="#edf4f8" '
        'style="width:100%;border-collapse:collapse;mso-table-lspace:0pt;mso-table-rspace:0pt;">'
        '<tr><td align="center" valign="top" style="padding:0;">'
        '<table role="presentation" width="900" cellspacing="0" cellpadding="0" border="0" align="center" '
        'style="width:900px;border-collapse:collapse;background:#fbfdff;mso-table-lspace:0pt;mso-table-rspace:0pt;">'
        '<tr><td align="left" bgcolor="#567b95" style="padding:30px 28px;font-family:Arial,Helvetica,sans-serif;'
        'color:#ffffff;text-align:left;">'
        '<div style="margin:0;font-size:28px;line-height:34px;font-weight:bold;">{} Preseason Newsletter</div>'
        '<div style="margin-top:7px;color:#e6eef3;font-size:13px;line-height:18px;">LeagueLab &#8226; {} &#8226; Draft complete. Season loading.</div>'
        '</td></tr><tr><td align="left" style="padding:0;text-align:left;">{}</td></tr>'
        '<tr><td align="center" style="padding:20px 28px;font-family:Arial,Helvetica,sans-serif;'
        'text-align:center;color:#8a9ba6;font-size:10px;">Generated by LeagueLab</td></tr>'
        '</table></td></tr></table></body></html>'
    ).format(_email_escape(season), _email_escape(league_name), _email_escape(season), content)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument(
        "--draft-analysis-json",
        action="store_true",
        help="Write joined draft pick/Yahoo ADP analysis JSON instead of newsletter HTML.",
    )
    args = parser.parse_args()

    if args.draft_analysis_json:
        path, rows = write_draft_analysis_report(args.season)
        print(path)
        print("Draft picks analyzed: {}".format(len(rows)))
        return

    html = build_preseason_html(args.season)
    email_html = build_preseason_email_html(args.season)
    out_dir = OUTPUT_ROOT / str(args.season)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "preseason_newsletter.html"
    email_path = out_dir / "preseason_newsletter_email.html"
    path.write_text(html, encoding="utf-8")
    email_path.write_text(email_html, encoding="utf-8-sig")
    print(path)
    print(email_path)


if __name__ == "__main__":
    main()
