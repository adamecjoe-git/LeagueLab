"""
LeagueLab weekly newsletter HTML renderer - pastel blue theme.

Python 3.8 compatible.
"""

from html import escape
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = PROJECT_ROOT / "data" / "output"


def _num(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _f(value, digits=2):
    try:
        return ("{:." + str(digits) + "f}").format(float(value))
    except (TypeError, ValueError):
        return "-"


def _pct(value):
    try:
        return "{:.1f}%".format(float(value) * 100.0)
    except (TypeError, ValueError):
        return "-"


def _record(row):
    w = int(_num(row.get("actual_wins")))
    l = int(_num(row.get("actual_losses")))
    t = int(_num(row.get("actual_ties")))
    return "{}-{}-{}".format(w, l, t) if t else "{}-{}".format(w, l)


def _movement(value):
    try:
        n = int(float(value))
    except (TypeError, ValueError):
        return "-"
    if n > 0:
        return "+{}".format(n)
    if n < 0:
        return str(n)
    return "-"


def _table(headers, rows, compact=False, row_classes=None):
    head = "".join("<th>{}</th>".format(escape(str(x))) for x in headers)
    body = []
    row_classes = row_classes or []
    for index, row in enumerate(rows):
        css_class = row_classes[index] if index < len(row_classes) else ""
        body.append(
            '<tr class="{}">{}</tr>'.format(
                css_class,
                "".join("<td>{}</td>".format(escape(str(x))) for x in row),
            )
        )
    cls = " compact" if compact else ""
    return (
        '<div class="table-wrap"><table class="{}"><thead><tr>{}</tr></thead>'
        "<tbody>{}</tbody></table></div>"
    ).format(cls.strip(), head, "".join(body))


def _card(label, value, detail=""):
    return (
        '<div class="card"><div class="card-label">{}</div>'
        '<div class="card-value">{}</div><div class="card-detail">{}</div></div>'
    ).format(escape(str(label)), escape(str(value)), escape(str(detail)))


def _highlight(label, value, detail=""):
    return (
        '<div class="highlight"><div class="highlight-label">{}</div>'
        '<div class="highlight-value">{}</div>'
        '<div class="highlight-detail">{}</div></div>'
    ).format(escape(str(label)), escape(str(value)), escape(str(detail)))


def _section(title, content, subtitle=""):
    subtitle_html = (
        '<div class="section-subtitle">{}</div>'.format(escape(subtitle))
        if subtitle else ""
    )
    return '<div class="section"><h2>{}</h2>{}{}</div>'.format(
        escape(title), subtitle_html, content
    )


def _build_matchups(glance):
    rankings = glance.get("weekly_rankings", []) if glance else []
    by_name = {
        str(row.get("team_name", "")): row
        for row in rankings if row.get("team_name")
    }
    seen = set()
    matchups = []

    for row in rankings:
        team = str(row.get("team_name", "") or "")
        opponent = str(row.get("opponent_team_name", "") or "")
        if not team or not opponent:
            continue
        key = tuple(sorted([team, opponent]))
        if key in seen:
            continue
        seen.add(key)

        opponent_row = by_name.get(opponent, {})
        team_score = _num(row.get("score"))
        opponent_score = row.get("opponent_points")
        if opponent_score is None:
            opponent_score = opponent_row.get("score")
        opponent_score = _num(opponent_score)

        if team_score >= opponent_score:
            winner, winner_score = team, team_score
            loser, loser_score = opponent, opponent_score
        else:
            winner, winner_score = opponent, opponent_score
            loser, loser_score = team, team_score

        matchups.append({
            "winner": winner,
            "winner_score": winner_score,
            "loser": loser,
            "loser_score": loser_score,
            "margin": abs(winner_score - loser_score),
        })

    matchups.sort(key=lambda item: item["winner_score"], reverse=True)
    return matchups


def _matchup_cards(matchups):
    cards = []
    for item in matchups:
        cards.append(
            '<div class="matchup">'
            '<div class="matchup-team winner"><span>{}</span><strong>{}</strong></div>'
            '<div class="matchup-team"><span>{}</span><strong>{}</strong></div>'
            '<div class="matchup-margin">Margin: {} pts</div></div>'.format(
                escape(item["winner"]), _f(item["winner_score"]),
                escape(item["loser"]), _f(item["loser_score"]),
                _f(item["margin"]),
            )
        )
    return '<div class="matchups">{}</div>'.format("".join(cards))


def _challenge_section(data):
    if not data:
        return ""

    standings = data.get("standings", [])
    standing_rows = [
        [row.get("rank", ""), row.get("team_name", ""), row.get("value", "")]
        for row in standings
    ]

    summary = '<div class="challenge-summary">'
    summary += _highlight("Challenge", data.get("name", "-"), data.get("weeks", ""))
    summary += _highlight("Status", data.get("status", "-"), "")
    summary += "</div>"

    content = summary
    content += '<h3>Current Standings</h3>'
    content += _table(["Rank", "Team", "Score"], standing_rows, compact=True)

    payouts = data.get("payout_leaderboard", [])
    if payouts:
        payout_rows = [
            [index, row.get("team_name", ""), "${:.0f}".format(_num(row.get("amount")))]
            for index, row in enumerate(payouts, 1)
        ]
        content += '<h3>Challenge Payout Leaders</h3>'
        content += _table(["Rank", "Team", "Winnings"], payout_rows, compact=True)

    season_points = data.get("season_points", [])
    if season_points:
        season_rows = [
            [row.get("rank", ""), row.get("team_name", ""), row.get("value", "")]
            for row in season_points
        ]
        label = "Season Points Winner" if data.get("season_points_complete") else "Season Points Race"
        content += "<h3>{}</h3>".format(label)
        content += _table(["Rank", "Team", "Points"], season_rows, compact=True)

    if data.get("next_challenge"):
        content += '<div class="callout"><strong>Up next:</strong> {}</div>'.format(
            escape(str(data["next_challenge"]))
        )

    return _section("Challenge Update", content)



def _admin_section(data):
    if not data:
        return ""

    content = ""
    dues = data.get("dues") or {}
    notes = data.get("notes") or []

    if dues:
        content += '<div class="admin-summary">'
        content += _highlight(
            "Dues Paid",
            "{} of {}".format(dues.get("paid_count", 0), dues.get("team_count", 0)),
            "${:.2f} collected".format(_num(dues.get("total_paid"))),
        )
        content += _highlight(
            "Outstanding",
            "{} team{}".format(
                dues.get("unpaid_count", 0),
                "" if int(dues.get("unpaid_count", 0) or 0) == 1 else "s",
            ),
            "${:.2f} remaining".format(_num(dues.get("balance_due"))),
        )
        content += "</div>"

        unpaid = dues.get("unpaid") or []
        if unpaid:
            chips = []
            for row in unpaid:
                balance = _num(row.get("balance_due"))
                chips.append(
                    '<span class="dues-chip">{} <strong>${:.0f}</strong></span>'.format(
                        escape(str(row.get("team_name") or "-")),
                        balance,
                    )
                )
            content += '<h3>Still Owed</h3><div class="dues-chips">{}</div>'.format(
                "".join(chips)
            )
        else:
            content += '<div class="paid-callout">All league dues are paid.</div>'

    if notes:
        content += '<h3>Commissioner Notes</h3><ul class="admin-notes">'
        for note in notes:
            content += '<li>{}</li>'.format(escape(str(note)))
        content += "</ul>"

    if not content:
        return ""

    return _section("League Admin", content)


def build_newsletter_html(
    season,
    week,
    analytics_result,
    league_name="XTreme Football",
    challenge_data=None,
    admin_data=None,
):
    glance = analytics_result.get("week_at_a_glance") or {}
    lineup_summary = analytics_result.get("lineup_summary") or {}

    weekly_rows = [
        row for row in analytics_result.get("weekly_analytics", [])
        if int(row.get("week", 0) or 0) == int(week)
    ]
    weekly_rows.sort(key=lambda row: int(_num(row.get("standings_rank"), 999)))

    power = sorted(
        analytics_result.get("power_rankings", []),
        key=lambda row: int(_num(row.get("power_rank"), 999)),
    )
    luck = sorted(
        analytics_result.get("luck", []),
        key=lambda row: _num(row.get("luck_wins")),
        reverse=True,
    )
    sos = sorted(
        analytics_result.get("schedule_strength", []),
        key=lambda row: int(_num(row.get("sos_rank"), 999)),
    )
    matchups = _build_matchups(glance)

    high = glance.get("highest_team_score") or {}
    low = glance.get("lowest_team_score") or {}
    top_starter = glance.get("top_starter") or {}
    top_bench = glance.get("top_bench_player") or {}
    closest = min(matchups, key=lambda x: x["margin"]) if matchups else {}
    blowout = max(matchups, key=lambda x: x["margin"]) if matchups else {}

    glance_html = '<div class="cards">'
    glance_html += _card("High Score", high.get("team_name", "-"), "{} pts".format(_f(high.get("score"))))
    glance_html += _card("Low Score", low.get("team_name", "-"), "{} pts".format(_f(low.get("score"))))
    glance_html += _card(
        "Closest Matchup",
        "{} vs {}".format(closest.get("winner", "-"), closest.get("loser", "-")),
        "{} pt margin".format(_f(closest.get("margin"))),
    )
    glance_html += _card(
        "Biggest Blowout",
        "{} over {}".format(blowout.get("winner", "-"), blowout.get("loser", "-")),
        "{} pt margin".format(_f(blowout.get("margin"))),
    )
    glance_html += _card(
        "Top Starter", top_starter.get("player_name", "-"),
        "{} pts • {}".format(_f(top_starter.get("points")), top_starter.get("team_name", "")).rstrip(" •"),
    )
    glance_html += _card(
        "Top Bench", top_bench.get("player_name", "-"),
        "{} pts • {}".format(_f(top_bench.get("points")), top_bench.get("team_name", "")).rstrip(" •"),
    )
    glance_html += "</div>"

    highlights = []
    best_eff = lineup_summary.get("best_efficiency") or {}
    most_left = lineup_summary.get("most_points_left") or {}
    worst_decision = lineup_summary.get("worst_decision") or {}

    if best_eff:
        highlights.append(_highlight(
            "Best Lineup", best_eff.get("team_name", "-"),
            "{}% efficient".format(_f(best_eff.get("lineup_efficiency"), 1)),
        ))
    if most_left:
        highlights.append(_highlight(
            "Most Points Left on Bench", most_left.get("team_name", "-"),
            "{} points".format(_f(most_left.get("points_left_on_bench"))),
        ))
    if worst_decision:
        highlights.append(_highlight(
            "Biggest Lineup Miss", worst_decision.get("team_name", "-"),
            "{} over {} (+{})".format(
                worst_decision.get("biggest_bench_player", "-"),
                worst_decision.get("replaced_starter", "-"),
                _f(worst_decision.get("decision_points_gained")),
            ),
        ))
    if closest:
        highlights.append(_highlight(
            "Nail-Biter",
            "{} over {}".format(closest["winner"], closest["loser"]),
            "{} point margin".format(_f(closest["margin"])),
        ))
    if blowout:
        highlights.append(_highlight(
            "Runaway",
            "{} over {}".format(blowout["winner"], blowout["loser"]),
            "{} point margin".format(_f(blowout["margin"])),
        ))
    if top_starter:
        highlights.append(_highlight(
            "Top Individual Performance",
            top_starter.get("player_name", "-"),
            "{} points for {}".format(
                _f(top_starter.get("points")), top_starter.get("team_name", "")
            ),
        ))

    highlights_html = '<div class="highlights">{}</div>'.format("".join(highlights))

    power_rows = []
    power_classes = []
    for index, row in enumerate(power):
        power_rows.append([
            row.get("power_rank", ""), row.get("team_name", ""),
            _f(row.get("power_score")), _f(row.get("season_points")),
            _pct(row.get("all_play_win_pct")), _f(row.get("recent_avg_points")),
            _record(row),
        ])
        power_classes.append("power-top" if index < 3 else "")
    power_html = _table(
        ["Rank", "Team", "Power", "PF", "All-Play", "Recent", "Record"],
        power_rows, row_classes=power_classes,
    )
    power_html += (
        '<div class="note">Formula: 30% season scoring • 25% all-play • '
        '35% recent form • 10% record</div>'
    )

    standings_rows = [
        [
            row.get("standings_rank", ""), row.get("team_name", ""), _record(row),
            _f(row.get("points_for")), _movement(row.get("standings_movement")),
            row.get("current_streak", ""),
        ]
        for row in weekly_rows
    ]
    standings_html = _table(
        ["Rank", "Team", "Record", "PF", "Move", "Streak"],
        standings_rows, compact=True,
    )

    analytics_cards = []
    if luck:
        analytics_cards.append(_highlight(
            "Luckiest", luck[0].get("team_name", "-"),
            "{:+.2f} wins vs expected".format(_num(luck[0].get("luck_wins"))),
        ))
        analytics_cards.append(_highlight(
            "Unluckiest", luck[-1].get("team_name", "-"),
            "{:+.2f} wins vs expected".format(_num(luck[-1].get("luck_wins"))),
        ))
    if weekly_rows:
        best_ap = max(weekly_rows, key=lambda row: _num(row.get("all_play_win_pct")))
        worst_ap = min(weekly_rows, key=lambda row: _num(row.get("all_play_win_pct")))
        analytics_cards.append(_highlight(
            "All-Play Leader", best_ap.get("team_name", "-"),
            "{} • {}-{}".format(
                _pct(best_ap.get("all_play_win_pct")),
                int(_num(best_ap.get("all_play_wins"))),
                int(_num(best_ap.get("all_play_losses"))),
            ),
        ))
        analytics_cards.append(_highlight(
            "All-Play Bottom", worst_ap.get("team_name", "-"),
            _pct(worst_ap.get("all_play_win_pct")),
        ))
    if sos:
        analytics_cards.append(_highlight(
            "Toughest Schedule", sos[0].get("team_name", "-"),
            "{} SOS • {} opp avg".format(
                _pct(sos[0].get("strength_of_schedule")),
                _f(sos[0].get("avg_opponent_score")),
            ),
        ))
        analytics_cards.append(_highlight(
            "Easiest Schedule", sos[-1].get("team_name", "-"),
            "{} SOS • {} opp avg".format(
                _pct(sos[-1].get("strength_of_schedule")),
                _f(sos[-1].get("avg_opponent_score")),
            ),
        ))

    analytics_html = '<div class="highlights">{}</div>'.format("".join(analytics_cards))
    analytics_html += (
        '<div class="note">Luck compares actual wins with all-play expected wins. '
        'SOS uses how each opponent performed in the specific week you faced them.</div>'
    )

    css = """
    * { box-sizing:border-box; }
    body { margin:0; background:#edf4f8; font-family:Arial,Helvetica,sans-serif; color:#243341; }
    .shell { max-width:920px; margin:0 auto; background:#ffffff; box-shadow:0 0 0 1px #dbe7ef; }
    .hero { padding:30px 32px; background:#567b95; color:#fff; }
    .hero h1 { margin:0; font-size:29px; line-height:1.1; }
    .hero p { margin:8px 0 0; color:#e8f2f8; font-size:14px; }
    .section { padding:24px 28px; border-bottom:1px solid #dce8ef; }
    .section h2 { margin:0 0 14px; font-size:20px; color:#365a72; }
    .section h3 { margin:18px 0 8px; font-size:14px; color:#4f7187; }
    .section-subtitle { margin:-7px 0 14px; color:#71899a; font-size:12px; }

    .cards { display:flex; flex-wrap:wrap; gap:10px; }
    .card { flex:1 1 29%; min-width:190px; padding:14px 15px;
            background:#f1f7fb; border:1px solid #d4e4ee; border-radius:9px; }
    .card:nth-child(2n) { background:#f5f3fb; }
    .card-label,.highlight-label { font-size:10px; text-transform:uppercase;
            letter-spacing:.7px; color:#63839a; font-weight:bold; }
    .card-value { margin-top:6px; font-size:16px; line-height:1.2; font-weight:bold; color:#29485d; }
    .card-detail { margin-top:5px; color:#6b8191; font-size:12px; }

    .matchups { display:grid; grid-template-columns:repeat(2,1fr); gap:10px; }
    .matchup { border:1px solid #d4e4ee; border-radius:9px; overflow:hidden; background:#fbfdff; }
    .matchup-team { display:flex; justify-content:space-between; gap:12px;
                    padding:10px 12px; border-bottom:1px solid #e1ebf1; font-size:13px; }
    .matchup-team.winner { font-weight:bold; background:#eaf4fa; color:#29485d; }
    .matchup-team strong { font-size:15px; }
    .matchup-margin { padding:7px 12px; color:#7890a0; font-size:10px;
                      text-transform:uppercase; letter-spacing:.4px; }

    .highlights { display:grid; grid-template-columns:repeat(3,1fr); gap:10px; }
    .highlight { padding:13px 14px; border-left:4px solid #88b6d2;
                 background:#f1f7fb; min-height:78px; }
    .highlight:nth-child(3n+2) { background:#f5f3fb; border-left-color:#b7abd5; }
    .highlight:nth-child(3n) { background:#eef8f6; border-left-color:#98c7bd; }
    .highlight-value { margin-top:5px; font-size:15px; font-weight:bold; color:#29485d; }
    .highlight-detail { margin-top:4px; font-size:12px; color:#6b8191; line-height:1.35; }

    .challenge-summary { display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-bottom:6px; }
    .admin-summary { display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-bottom:8px; }
    .dues-chips { display:flex; flex-wrap:wrap; gap:7px; }
    .dues-chip { display:inline-block; padding:7px 10px; background:#f5f3fb;
                 border:1px solid #ddd6ef; border-radius:16px; font-size:11px; color:#536b7b; }
    .dues-chip strong { color:#365a72; }
    .paid-callout { padding:10px 12px; background:#eef8f6; border:1px solid #cee5df;
                    border-radius:7px; color:#4f756d; font-size:12px; font-weight:bold; }
    .admin-notes { margin:0; padding-left:20px; color:#536b7b; font-size:12px; line-height:1.6; }

    .table-wrap { overflow-x:auto; }
    table { width:100%; border-collapse:collapse; font-size:12px; }
    th { text-align:left; background:#eaf3f8; padding:8px 7px;
         border-bottom:2px solid #bdd3df; color:#365a72; white-space:nowrap; }
    td { padding:8px 7px; border-bottom:1px solid #dce8ef; white-space:nowrap; }
    tr.power-top td { background:#f1f7fb; font-weight:bold; }
    tr.power-top:first-child td { background:#e1f0f8; color:#29485d; }
    table.compact td { padding-top:7px; padding-bottom:7px; }

    .note { color:#71899a; font-size:11px; margin-top:10px; line-height:1.4; }
    .callout { margin-top:12px; padding:10px 12px; background:#eaf4fa;
               border:1px solid #d2e5ef; border-radius:7px; font-size:12px; color:#365a72; }
    .footer { padding:20px 28px; color:#8196a4; background:#f4f8fa;
              font-size:10px; text-align:center; }

    @media(max-width:650px) {
      .hero,.section { padding-left:16px; padding-right:16px; }
      .matchups,.highlights,.challenge-summary,.admin-summary { grid-template-columns:1fr; }
      .card { min-width:46%; }
      table { font-size:11px; }
    }
    """

    parts = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        "<title>LeagueLab Week {}</title><style>{}</style></head><body>".format(week, css),
        '<div class="shell">',
        '<div class="hero"><h1>{}</h1><p>LeagueLab • {} • Week {} Recap</p></div>'.format(
            escape(league_name), season, week
        ),
        _section("Week at a Glance", glance_html),
        _section("Matchup Results", _matchup_cards(matchups)),
        _section("Week Highlights", highlights_html),
        _challenge_section(challenge_data),
        _section("Power Rankings", power_html),
        _section("Standings", standings_html),
        _section("Analytics Corner", analytics_html),
        _admin_section(admin_data),
        '<div class="footer">Generated by LeagueLab</div>',
        "</div></body></html>",
    ]
    return "".join(parts)


def write_newsletter(
    season, week, analytics_result, league_name="XTreme Football",
    challenge_data=None, admin_data=None,
):
    output_dir = OUTPUT_ROOT / str(season) / "newsletter"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "week_{:02d}.html".format(int(week))
    html = build_newsletter_html(
        season=season, week=week, analytics_result=analytics_result,
        league_name=league_name, challenge_data=challenge_data,
        admin_data=admin_data,
    )
    with path.open("w", encoding="utf-8") as handle:
        handle.write(html)
    return path
