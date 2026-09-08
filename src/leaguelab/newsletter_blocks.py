"""Reusable HTML blocks for LeagueLab newsletters. Python 3.8 compatible."""
from html import escape


def num(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def f(value, digits=2):
    try:
        return ("{: ." + str(digits) + "f}").format(float(value)).strip()
    except (TypeError, ValueError):
        return "-"


def pct(value):
    try:
        return "{:.1f}%".format(float(value) * 100.0)
    except (TypeError, ValueError):
        return "-"


def record(row):
    w = int(num(row.get("actual_wins")))
    l = int(num(row.get("actual_losses")))
    t = int(num(row.get("actual_ties")))
    return "{}-{}-{}".format(w, l, t) if t else "{}-{}".format(w, l)


def movement(value):
    try:
        n = int(float(value))
    except (TypeError, ValueError):
        return "-"
    return "+{}".format(n) if n > 0 else (str(n) if n < 0 else "-")


def section(title, content, subtitle=""):
    if not content:
        return ""
    sub = '<div class="section-subtitle">{}</div>'.format(escape(str(subtitle))) if subtitle else ""
    return '<div class="section"><h2>{}</h2>{}{}</div>'.format(escape(str(title)), sub, content)


def table(headers, rows, compact=False):
    if not rows:
        return ""
    head = "".join("<th>{}</th>".format(escape(str(x))) for x in headers)
    body = "".join(
        "<tr>{}</tr>".format("".join("<td>{}</td>".format(escape(str(x))) for x in row))
        for row in rows
    )
    return '<div class="table-wrap"><table class="{}"><thead><tr>{}</tr></thead><tbody>{}</tbody></table></div>'.format(
        "compact" if compact else "", head, body
    )


def highlight(label, value, detail=""):
    return '<div class="highlight"><div class="highlight-label">{}</div><div class="highlight-value">{}</div><div class="highlight-detail">{}</div></div>'.format(
        escape(str(label)), escape(str(value)), escape(str(detail))
    )


def build_matchups(glance):
    rankings = (glance or {}).get("weekly_rankings", [])
    by_name = {str(r.get("team_name", "")): r for r in rankings if r.get("team_name")}
    seen = set()
    output = []
    for row in rankings:
        team = str(row.get("team_name", "") or "")
        opponent = str(row.get("opponent_team_name", "") or "")
        if not team or not opponent:
            continue
        key = tuple(sorted([team, opponent]))
        if key in seen:
            continue
        seen.add(key)
        team_score = num(row.get("score"))
        opponent_score = num(row.get("opponent_points", by_name.get(opponent, {}).get("score")))
        if team_score >= opponent_score:
            winner, winner_score, loser, loser_score = team, team_score, opponent, opponent_score
        else:
            winner, winner_score, loser, loser_score = opponent, opponent_score, team, team_score
        output.append({
            "winner": winner,
            "winner_score": winner_score,
            "loser": loser,
            "loser_score": loser_score,
            "margin": abs(winner_score - loser_score),
        })
    output.sort(key=lambda x: x["winner_score"], reverse=True)
    return output


def matchup_cards(matchups):
    cards = []
    for item in matchups:
        cards.append(
            '<div class="matchup"><div class="matchup-team winner"><span>{}</span><strong>{}</strong></div>'
            '<div class="matchup-team"><span>{}</span><strong>{}</strong></div>'
            '<div class="matchup-margin">Margin: {} pts</div></div>'.format(
                escape(str(item["winner"])), f(item["winner_score"]),
                escape(str(item["loser"])), f(item["loser_score"]), f(item["margin"])
            )
        )
    return '<div class="matchups">{}</div>'.format("".join(cards)) if cards else ""


def matchup_results(ctx):
    return section("Matchup Results", matchup_cards(ctx["matchups"]))


def weekly_highlights(ctx):
    glance = ctx.get("glance") or {}
    summary = ctx.get("lineup_summary") or {}
    matchups = ctx.get("matchups") or []

    high = glance.get("highest_team_score") or {}
    low = glance.get("lowest_team_score") or {}
    starter = glance.get("top_starter") or {}
    bench = glance.get("top_bench_player") or {}
    best = summary.get("best_efficiency") or {}
    left = summary.get("most_points_left") or {}
    miss = summary.get("worst_decision") or {}

    close = min(matchups, key=lambda x: x["margin"]) if matchups else {}
    blow = max(matchups, key=lambda x: x["margin"]) if matchups else {}

    # The highlight grid renders row-by-row. This ordering produces:
    # Column 1: High Score / Low Score / Top Individual Performance
    # Column 2: Biggest Blowout / Closest Matchup / Best Lineup
    # Column 3: Most Points Left on Bench / Biggest Lineup Miss / Top Bench Player
    rows = [
        (
            highlight("High Score", high.get("team_name", "-"), "{} pts".format(f(high.get("score")))) if high else "",
            highlight("Biggest Blowout", "{} over {}".format(blow["winner"], blow["loser"]), "{} pt margin".format(f(blow["margin"]))) if blow else "",
            highlight("Most Points Left on Bench", left.get("team_name", "-"), "{} points".format(f(left.get("points_left_on_bench")))) if left else "",
        ),
        (
            highlight("Low Score", low.get("team_name", "-"), "{} pts".format(f(low.get("score")))) if low else "",
            highlight("Closest Matchup", "{} over {}".format(close["winner"], close["loser"]), "{} pt margin".format(f(close["margin"]))) if close else "",
            highlight("Biggest Lineup Miss", miss.get("team_name", "-"), "{} over {} (+{})".format(
                miss.get("biggest_bench_player", "-"),
                miss.get("replaced_starter", "-"),
                f(miss.get("decision_points_gained")),
            )) if miss else "",
        ),
        (
            highlight("Top Individual Performance", starter.get("player_name", "-"), "{} pts • {}".format(
                f(starter.get("points")), starter.get("team_name", "")
            ).rstrip(" •")) if starter else "",
            highlight("Best Lineup", best.get("team_name", "-"), "{}% efficient".format(
                f(best.get("lineup_efficiency"), 1)
            )) if best else "",
            highlight("Top Bench Player", bench.get("player_name", "-"), "{} pts • {}".format(
                f(bench.get("points")), bench.get("team_name", "")
            ).rstrip(" •")) if bench else "",
        ),
    ]

    items = [item for row in rows for item in row if item]
    return section(
        "Weekly Highlights",
        '<div class="highlights">{}</div>'.format("".join(items)),
    )


def standings(ctx, final=False):
    rows = [[
        r.get("standings_rank", ""), r.get("team_name", ""), record(r), f(r.get("points_for")),
        movement(r.get("standings_movement")), r.get("current_streak", "")
    ] for r in ctx.get("weekly_rows", [])]
    title = "Final Regular-Season Standings" if final else "Standings"
    return section(title, table(["Rank", "Team", "Record", "PF", "Move", "Streak"], rows, True))


def power_rankings(ctx, final=False):
    rows = [[
        r.get("power_rank", ""), r.get("team_name", ""), f(r.get("power_score")), f(r.get("season_points")),
        pct(r.get("all_play_win_pct")), f(r.get("recent_avg_points")), record(r)
    ] for r in ctx.get("power", [])]
    content = table(["Rank", "Team", "Power", "PF", "All-Play", "Recent", "Record"], rows)
    if content:
        content += '<div class="note">Formula: 30% season scoring • 25% all-play • 35% recent form • 10% record</div>'
    return section("Final Regular-Season Power Rankings" if final else "Power Rankings", content)


def _challenge_header(data, result=False):
    if not data:
        return ""
    pieces = [
        highlight(
            "Challenge",
            data.get("name", "-"),
            "{} • ${} prize".format(data.get("weeks", ""), data.get("prize", 10)),
        )
    ]
    description = data.get("description") or ""
    if description:
        pieces.append(
            '<div class="challenge-description">{}</div>'.format(
                escape(str(description))
            )
        )
    return '<div class="highlights">{}</div>'.format(
        "".join(x for x in pieces if x)
    )


def challenge_update(ctx):
    return section("Challenge Update", _challenge_header(ctx.get("challenge_data"), False))


def challenge_results(ctx):
    return section("Challenge Results", _challenge_header(ctx.get("challenge_data"), True))


def _challenge_standings_table(headers, rows, complete=False):
    if not rows:
        return ""

    head = "".join(
        "<th>{}</th>".format(escape(str(value)))
        for value in headers
    )
    body_rows = []

    for index, row in enumerate(rows):
        cells = "".join(
            "<td>{}</td>".format(escape(str(value)))
            for value in row
        )
        if index == 0:
            label = "winner" if complete else "leader"
            body_rows.append(
                '<tr style="font-size:14px;font-weight:bold;background:#f0f7fb;" '
                'title="{}">{}</tr>'.format(label, cells)
            )
        else:
            body_rows.append("<tr>{}</tr>".format(cells))

    return (
        '<div class="table-wrap"><table class="compact">'
        "<thead><tr>{}</tr></thead><tbody>{}</tbody></table></div>"
    ).format(head, "".join(body_rows))


def challenge_standings(ctx, force=False):
    data = ctx.get("challenge_data") or {}
    if not data:
        return ""

    rows = [
        [r.get("rank", ""), r.get("team_name", ""), r.get("value", "")]
        for r in data.get("standings", [])
    ]
    content = _challenge_standings_table(
        ["Rank", "Team", "Score"],
        rows,
        complete=bool(data.get("complete")),
    )
    return section("Challenge Standings", content)


def challenge_leaderboard(ctx):
    """Season-to-date challenge payout leaderboard; even weeks only."""
    week = int(ctx.get("week", 0))
    if week < 2 or week > 14 or week % 2 != 0:
        return ""

    data = ctx.get("challenge_data") or {}
    leaderboard = (
        data.get("payout_leaderboard")
        or data.get("payouts")
        or []
    )
    if not leaderboard:
        return ""

    rows = []
    for index, row in enumerate(leaderboard):
        rows.append([
            row.get("rank", index + 1),
            row.get("team_name", row.get("team", "")),
            row.get(
                "challenge_wins",
                row.get("wins", row.get("challenges_won", "")),
            ),
            "${:.0f}".format(
                float(
                    row.get(
                        "amount",
                        row.get(
                            "amount_won",
                            row.get("payout", row.get("winnings", 0)),
                        ),
                    )
                    or 0
                )
            ),
        ])

    return section(
        "Challenge Leaderboard",
        table(
            ["Rank", "Team", "Challenge Wins", "Winnings"],
            rows,
            True,
        ),
    )


def next_challenge(ctx):
    # Announce the next challenge only after the current two-week challenge
    # finishes. Week 14 has no next regular-season challenge.
    week = int(ctx.get("week", 0))
    if week < 2 or week >= 14 or week % 2 != 0:
        return ""

    data = ctx.get("challenge_data") or {}
    nxt = data.get("next_challenge") or {}
    if not isinstance(nxt, dict) or not nxt:
        return ""

    content = '<div class="highlights">{}</div>'.format(
        highlight(
            "Up Next",
            nxt.get("name", "-"),
            "{} • ${} prize".format(
                nxt.get("weeks", ""),
                nxt.get("prize", 10),
            ),
        )
    )
    if nxt.get("description"):
        content += '<div class="challenge-description">{}</div>'.format(
            escape(str(nxt["description"]))
        )

    return section("Next Challenge", content)


def beyond_box_score(ctx, season=False):
    season_luck = ctx.get("luck") or []
    weekly_rows = ctx.get("all_play_week") or []
    sos = ctx.get("sos") or []

    weekly_overachiever = ""
    weekly_luckiest = ""
    weekly_unluckiest = ""
    season_all_play_leader = ""
    season_luckiest = ""
    season_unluckiest = ""
    season_all_play_bottom = ""
    season_toughest_sos = ""
    season_weakest_sos = ""

    if weekly_rows and not season:
        projected_rows = [
            row for row in weekly_rows
            if num(row.get("projected_points")) > 0
        ]

        if projected_rows:
            best = max(
                projected_rows,
                key=lambda r: (
                    num(r.get("points"))
                    - num(r.get("projected_points"))
                ),
            )
            delta = (
                num(best.get("points"))
                - num(best.get("projected_points"))
            )
            weekly_overachiever = highlight(
                "This Week • Overachiever",
                best.get("team_name", "-"),
                "{:+.2f} vs projection".format(delta),
            )
        else:
            # Fallback for historical data without Yahoo projections:
            # compare this week's score with the team's average entering
            # the week. This keeps the metric meaningful without inventing
            # projection data.
            current_week = int(ctx.get("week", 0))
            history = ctx.get("all_weekly_rows") or []
            prior_by_team = {}
            for history_row in history:
                if int(num(history_row.get("week"))) >= current_week:
                    continue
                key = str(history_row.get("team_key") or "")
                prior_by_team.setdefault(key, []).append(
                    num(history_row.get("weekly_score"))
                )

            candidates = []
            for row in weekly_rows:
                key = str(row.get("team_key") or "")
                prior = prior_by_team.get(key) or []
                if prior:
                    prior_avg = sum(prior) / len(prior)
                    candidates.append((
                        num(row.get("points")) - prior_avg,
                        row,
                        prior_avg,
                    ))

            if candidates:
                delta, best, prior_avg = max(
                    candidates,
                    key=lambda item: item[0],
                )
                weekly_overachiever = highlight(
                    "This Week • Overachiever",
                    best.get("team_name", "-"),
                    "{:+.2f} vs entering avg".format(delta),
                )

        def weekly_luck(row):
            result = str(row.get("actual_result") or "").upper()
            actual = 1.0 if result == "W" else (0.5 if result == "T" else 0.0)
            return actual - num(row.get("expected_weekly_wins"))

        lucky = max(weekly_rows, key=weekly_luck)
        unlucky = min(weekly_rows, key=weekly_luck)
        weekly_luckiest = highlight(
            "This Week • Luckiest",
            lucky.get("team_name", "-"),
            "{:+.2f} win luck".format(weekly_luck(lucky)),
        )
        weekly_unluckiest = highlight(
            "This Week • Unluckiest",
            unlucky.get("team_name", "-"),
            "{:+.2f} win luck".format(weekly_luck(unlucky)),
        )

    if season_luck:
        season_luckiest = highlight(
            "Season • Luckiest",
            season_luck[0].get("team_name", "-"),
            "{:+.2f} wins vs expected".format(
                num(season_luck[0].get("luck_wins"))
            ),
        )
        season_unluckiest = highlight(
            "Season • Unluckiest",
            season_luck[-1].get("team_name", "-"),
            "{:+.2f} wins vs expected".format(
                num(season_luck[-1].get("luck_wins"))
            ),
        )

    current = ctx.get("weekly_rows") or []
    if current:
        best_season = max(current, key=lambda r: num(r.get("all_play_win_pct")))
        worst_season = min(current, key=lambda r: num(r.get("all_play_win_pct")))
        season_all_play_leader = highlight(
            "Season • All-Play Leader",
            best_season.get("team_name", "-"),
            pct(best_season.get("all_play_win_pct")),
        )
        season_all_play_bottom = highlight(
            "Season • All-Play Bottom",
            worst_season.get("team_name", "-"),
            pct(worst_season.get("all_play_win_pct")),
        )

    if sos:
        season_toughest_sos = highlight(
            "Season • Toughest SOS",
            sos[0].get("team_name", "-"),
            "{} SOS • {} opp avg".format(
                pct(sos[0].get("strength_of_schedule")),
                f(sos[0].get("avg_opponent_score")),
            ),
        )
        season_weakest_sos = highlight(
            "Season • Weakest SOS",
            sos[-1].get("team_name", "-"),
            "{} SOS • {} opp avg".format(
                pct(sos[-1].get("strength_of_schedule")),
                f(sos[-1].get("avg_opponent_score")),
            ),
        )

    if season:
        # Season Edition contains only season-long measures.
        items = [
            season_all_play_leader,
            season_all_play_bottom,
            season_luckiest,
            season_unluckiest,
            season_toughest_sos,
            season_weakest_sos,
        ]
    else:
        # Row-major order for the 3-column grid:
        # C1 Weekly: Overachiever / Luckiest / Unluckiest
        # C2 Season: All-Play Leader / Luckiest / Unluckiest
        # C3 Season: All-Play Bottom / Toughest SOS / Weakest SOS
        rows = [
            (
                weekly_overachiever,
                season_all_play_leader,
                season_all_play_bottom,
            ),
            (
                weekly_luckiest,
                season_luckiest,
                season_toughest_sos,
            ),
            (
                weekly_unluckiest,
                season_unluckiest,
                season_weakest_sos,
            ),
        ]
        items = [item for row in rows for item in row if item]

    title = (
        "Beyond the Box Score — Season Edition"
        if season
        else "Beyond the Box Score"
    )
    note = (
        "Weekly luck compares the matchup result with that week's all-play "
        "expectation. Season luck and SOS are through this newsletter week."
    )
    return section(
        title,
        '<div class="highlights">{}</div><div class="note">{}</div>'.format(
            "".join(item for item in items if item),
            escape(note),
        ),
    )


def upcoming_matchups(ctx, title="Next Week's Matchups"):
    data = ctx.get("upcoming_data") or {}
    matchups = data.get("matchups", [])
    if not matchups:
        return ""
    cards = []
    for index, item in enumerate(matchups):
        a, b = item["team_a"], item["team_b"]
        ar = "#{}".format(a["power_rank"]) if a.get("power_rank") else "#-"
        br = "#{}".format(b["power_rank"]) if b.get("power_rank") else "#-"
        watch = '<div class="watch">Matchup to Watch</div>' if index == data.get("matchup_to_watch") else ""
        ap = a.get("projected_points")
        bp = b.get("projected_points")
        ap_html = (
            ' <span class="projection">• Proj {}</span>'.format(f(ap))
            if ap is not None and num(ap) > 0 else ""
        )
        bp_html = (
            ' <span class="projection">• Proj {}</span>'.format(f(bp))
            if bp is not None and num(bp) > 0 else ""
        )
        cards.append('<div class="upcoming">{}<div><strong>{} {}</strong> <span>({})</span>{}</div><div class="versus">vs</div><div><strong>{} {}</strong> <span>({})</span>{}</div></div>'.format(
            watch, ar, escape(a["team_name"]), escape(a["record"]), ap_html, br, escape(b["team_name"]), escape(b["record"]), bp_html
        ))
    subtitle = "Week {} • Rank shown is LeagueLab Power Ranking".format(data.get("week", ""))
    return section(title, '<div class="upcoming-grid">{}</div>'.format("".join(cards)), subtitle)



def _next_round_card(item, label):
    if not item:
        return ""
    a = item.get("team_a") or {}
    b = item.get("team_b") or {}
    if not a or not b:
        return ""

    def team_line(team):
        projection = team.get("projected_points")
        projection_html = (
            ' <span class="projection">• Proj {}</span>'.format(f(projection))
            if projection is not None and num(projection) > 0
            else ""
        )
        return '<strong>#{} {}</strong>{}'.format(
            team.get("seed", "-"),
            escape(str(team.get("team_name", "-"))),
            projection_html,
        )

    return (
        '<div class="upcoming"><div class="watch">{}</div>'
        '<div>{}</div><div class="versus">vs</div><div>{}</div></div>'
    ).format(
        escape(str(label)),
        team_line(a),
        team_line(b),
    )


def _toilet_as_bracket_matchup(item):
    if not item:
        return None
    return {
        "team_a": {
            "seed": item.get("team_a_seed"),
            "team_key": item.get("team_a_key"),
            "team_name": item.get("team_a_name"),
            "projected_points": item.get("team_a_projected_points"),
        },
        "team_b": {
            "seed": item.get("team_b_seed"),
            "team_key": item.get("team_b_key"),
            "team_name": item.get("team_b_name"),
            "projected_points": item.get("team_b_projected_points"),
        },
    }


def next_round_matchups(ctx):
    """Postseason-aware next-round preview, including the Toilet Bowl."""
    week = int(ctx.get("week", 0))
    data = ctx.get("postseason_data") or {}
    playoff = data.get("playoff") or {}
    toilet = data.get("toilet_bowl") or {}
    cards = []
    next_week = week + 1

    if week == 14:
        for item in playoff.get("quarterfinals") or []:
            cards.append(_next_round_card(item, "Playoff Quarterfinal"))
        for pair in toilet.get("preview") or []:
            cards.append(_next_round_card(pair, "Toilet Bowl Semifinal"))

    elif week == 15:
        for item in playoff.get("championship_semifinals") or []:
            cards.append(_next_round_card(item, "Playoff Semifinal"))
        for item in playoff.get("consolation_semifinals") or []:
            cards.append(_next_round_card(item, "Consolation Semifinal"))
        toilet_final = _toilet_as_bracket_matchup(
            toilet.get("championship")
        )
        if toilet_final:
            cards.append(_next_round_card(toilet_final, "Toilet Bowl Final"))

    elif week == 16:
        finals = playoff.get("finals") or {}
        labels = (
            ("championship", "Championship"),
            ("third_place", "3rd Place"),
            ("fifth_place", "5th Place"),
            ("seventh_place", "7th Place"),
        )
        for key, label in labels:
            if finals.get(key):
                cards.append(_next_round_card(finals[key], label))

    cards = [card for card in cards if card]
    if not cards:
        return ""

    return section(
        "Next Round Matchups",
        '<div class="upcoming-grid">{}</div>'.format("".join(cards)),
        "Week {} • Final regular-season seeds shown".format(next_week),
    )


def season_accolades(ctx):
    if int(ctx.get("week", 0)) < 17:
        return ""
    try:
        from leaguelab.season_accolades import build_season_accolades
        awards = build_season_accolades(ctx.get("season"))
    except (ImportError, OSError, ValueError):
        awards = []

    if not awards:
        return ""

    cards = []
    for award in awards:
        cards.append(
            '<div class="accolade-card">'
            '<div class="accolade-icon">{}</div>'
            '<div class="accolade-title">{}</div>'
            '<div class="accolade-winner">{}</div>'
            '<div class="accolade-detail">{}</div>'
            '</div>'.format(
                escape(str(award.get("icon", ""))),
                escape(str(award.get("title", ""))),
                escape(str(award.get("winner", "-"))),
                escape(str(award.get("detail", ""))),
            )
        )
    return section(
        "Season Accolades",
        '<div class="accolades">{}</div>'.format("".join(cards)),
    )


def league_admin(ctx):
    data = ctx.get("admin_data") or {}
    if not data:
        return ""
    dues = data.get("dues") if isinstance(data.get("dues"), dict) else data
    content = []
    if dues and ("paid_count" in dues or "unpaid_count" in dues):
        content.append('<div class="highlights">{}{}</div>'.format(
            highlight("Dues Paid", "{} of {}".format(dues.get("paid_count", 0), dues.get("team_count", 0)), "${:.0f} collected".format(num(dues.get("total_paid")))),
            highlight("Outstanding", dues.get("unpaid_count", 0), "${:.0f} remaining".format(num(dues.get("balance_due"))))
        ))
        owed = dues.get("unpaid") or dues.get("unpaid_teams") or dues.get("still_owed") or []
        if owed:
            content.append('<div class="owed">{}</div>'.format("".join(
                '<span>{} — ${:.0f}</span>'.format(escape(str(x.get("team_name", ""))), num(x.get("balance_due", x.get("balance", 0)))) for x in owed
            )))
        elif dues.get("unpaid_count", 0) == 0:
            content.append('<div class="callout">All league dues are paid.</div>')
    notes = data.get("notes") or data.get("items") or []
    if isinstance(notes, str):
        notes = [notes]
    if notes:
        content.append('<h3>Commissioner Notes</h3><ul class="admin-list">{}</ul>'.format("".join('<li>{}</li>'.format(escape(str(x))) for x in notes)))
    return section("League Admin", "".join(content))


def losers_trophy(ctx):
    rows = ctx.get("weekly_rows") or []
    if not rows:
        return ""
    loser = max(rows, key=lambda r: int(num(r.get("standings_rank"), 0)))
    return section("Loser's Trophy", highlight("12th Place", loser.get("team_name", "-"), "Regular-season finish"))


def _bracket_team(team, winner_key=None):
    if not team:
        return '<div class="bracket-team bracket-team-empty">TBD</div>'
    winner = bool(
        winner_key
        and str(team.get("team_key") or "") == str(winner_key)
    )
    if winner:
        classes = "bracket-team winner"
    elif winner_key:
        classes = "bracket-team loser"
    else:
        classes = "bracket-team"
    score = team.get("score")
    projection = team.get("projected_points")
    if score is not None:
        score_html = '<span class="bracket-score">{}</span>'.format(f(score))
    elif projection is not None and num(projection) > 0:
        score_html = '<span class="bracket-score bracket-projection">Proj {}</span>'.format(f(projection))
    else:
        score_html = ""
    return (
        '<div class="{}"><span class="bracket-seed">#{}</span>'
        '<span class="bracket-name">{}</span>{}</div>'
    ).format(
        classes,
        team.get("seed", "-"),
        escape(str(team.get("team_name", "-"))),
        score_html,
    )


def _bracket_matchup(item, label):
    if not item:
        return (
            '<div class="bracket-matchup pending">'
            '<div class="bracket-label">{}</div>'
            '<div class="bracket-team bracket-team-empty">TBD</div>'
            '<div class="bracket-team bracket-team-empty">TBD</div></div>'
        ).format(escape(str(label)))
    return (
        '<div class="bracket-matchup"><div class="bracket-label">{}</div>'
        '{}{}</div>'
    ).format(
        escape(str(label)),
        _bracket_team(item.get("team_a"), item.get("winner_key")),
        _bracket_team(item.get("team_b"), item.get("winner_key")),
    )


def _playoff_bracket_html(playoff):
    if not playoff:
        return ""

    qfs = playoff.get("quarterfinals") or []
    semis = playoff.get("championship_semifinals") or []
    consolation = playoff.get("consolation_semifinals") or []
    finals = playoff.get("finals") or {}

    qf_html = "".join(
        _bracket_matchup(item, "Quarterfinal") for item in qfs
    )
    championship_sf = "".join(
        _bracket_matchup(
            semis[index] if index < len(semis) else None,
            "Semifinal",
        )
        for index in range(2)
    )
    consolation_sf = "".join(
        _bracket_matchup(
            consolation[index] if index < len(consolation) else None,
            "Consolation Semifinal",
        )
        for index in range(2)
    )

    return (
        '<div class="bracket-group">'
        '<div class="bracket-heading">Championship Bracket</div>'
        '<div class="bracket bracket-main">'
        '<div class="bracket-round bracket-qf">{}</div>'
        '<div class="bracket-round bracket-sf">{}</div>'
        '<div class="bracket-round bracket-final">{}{}</div>'
        '</div>'
        '<div class="bracket-heading bracket-heading-secondary">'
        'Consolation / Placement Bracket</div>'
        '<div class="bracket bracket-consolation">'
        '<div class="bracket-round bracket-qf-source">'
        '<div class="bracket-source-note">Quarterfinal losers</div></div>'
        '<div class="bracket-round bracket-sf">{}</div>'
        '<div class="bracket-round bracket-final">{}{}</div>'
        '</div></div>'
    ).format(
        qf_html,
        championship_sf,
        _bracket_matchup(finals.get("championship"), "Final"),
        _bracket_matchup(finals.get("third_place"), "3rd Place"),
        consolation_sf,
        _bracket_matchup(finals.get("fifth_place"), "5th Place"),
        _bracket_matchup(finals.get("seventh_place"), "7th Place"),
    )


def playoff_preview(ctx):
    playoff = (ctx.get("postseason_data") or {}).get("playoff") or {}
    return section(
        "Playoff Bracket / Preview",
        _playoff_bracket_html(playoff),
        "Seeds are final regular-season standings.",
    )


def playoff_results(ctx):
    playoff = (ctx.get("postseason_data") or {}).get("playoff") or {}
    return section(
        "Playoff Bracket",
        _playoff_bracket_html(playoff),
        "Seeds are final regular-season standings. Completed matchup winners are highlighted.",
    )


def _toilet_matchup(item, label):
    if not item:
        return _bracket_matchup(None, label)
    return _bracket_matchup({
        "team_a": {
            "seed": item.get("team_a_seed"),
            "team_key": item.get("team_a_key"),
            "team_name": item.get("team_a_name"),
            "score": item.get("team_a_score"),
            "projected_points": item.get("team_a_projected_points"),
        },
        "team_b": {
            "seed": item.get("team_b_seed"),
            "team_key": item.get("team_b_key"),
            "team_name": item.get("team_b_name"),
            "score": item.get("team_b_score"),
            "projected_points": item.get("team_b_projected_points"),
        },
        "winner_key": item.get("winner_key"),
    }, label)


def _toilet_bracket_html(data):
    if not data:
        return ""

    semis = data.get("semifinals") or []
    if semis:
        semi_html = "".join(
            _toilet_matchup(item, "Semifinal") for item in semis
        )
    else:
        semi_html = "".join(
            _bracket_matchup({
                "team_a": pair.get("team_a"),
                "team_b": pair.get("team_b"),
                "winner_key": None,
            }, "Semifinal")
            for pair in (data.get("preview") or [])
        )

    return (
        '<div class="bracket-group"><div class="bracket-heading">'
        'Toilet Bowl</div><div class="bracket bracket-toilet">'
        '<div class="bracket-round bracket-sf">{}</div>'
        '<div class="bracket-round bracket-final">{}</div>'
        '</div></div>'
    ).format(
        semi_html,
        _toilet_matchup(data.get("championship"), "Final"),
    )


def toilet_bowl_preview(ctx):
    toilet = (ctx.get("postseason_data") or {}).get("toilet_bowl") or {}
    return section(
        "Toilet Bowl Bracket / Preview",
        _toilet_bracket_html(toilet),
        "Seeds are final regular-season standings.",
    )


def toilet_bowl(ctx):
    toilet = (ctx.get("postseason_data") or {}).get("toilet_bowl") or {}
    return section(
        "Toilet Bowl Bracket",
        _toilet_bracket_html(toilet),
        "Seeds are final regular-season standings. Completed matchup winners are highlighted.",
    )


def league_champion(ctx):
    if int(ctx.get("week", 0)) < 17:
        return ""
    champion = ((ctx.get("postseason_data") or {}).get("playoff") or {}).get("champion") or {}
    if not champion:
        return ""
    return section(
        "League Champion",
        '<div class="champion-block"><div class="champion-kicker">'
        'League Champion</div><div class="champion-name">#{} {}</div></div>'.format(
            champion.get("seed", "-"),
            escape(str(champion.get("team_name", "-"))),
        ),
    )


def toilet_bowl_winner(ctx):
    if int(ctx.get("week", 0)) < 17:
        return ""
    champion = ((ctx.get("postseason_data") or {}).get("toilet_bowl") or {}).get("champion") or {}
    if not champion:
        return ""
    return section(
        "Toilet Bowl Champion",
        '<div class="champion-block"><div class="champion-kicker">'
        'Toilet Bowl Champion</div><div class="champion-name">#{} {}</div>'
        '<div class="champion-detail">${:.0f} payout</div></div>'.format(
            champion.get("seed", "-"),
            escape(str(champion.get("team_name", "-"))),
            num(champion.get("payout")),
        ),
    )


def championship_matchup(ctx):
    data = ctx.get("upcoming_data") or {}
    return upcoming_matchups(ctx, "Championship Matchup") if data.get("matchups") else ""


def challenge_winners(ctx):
    winners = (ctx.get("challenge_data") or {}).get("challenge_winners", [])
    if not winners:
        return ""

    rows = [
        [
            row.get("name", ""),
            row.get("team_name", ""),
            "${:.0f}".format(num(row.get("prize"))),
        ]
        for row in winners
    ]
    return section(
        "Challenge Winners",
        table(["Challenge", "Winner", "Prize"], rows, True),
    )


def challenge_payout_leaderboard(ctx):
    leaderboard = (
        (ctx.get("challenge_data") or {}).get("payout_leaderboard", [])
    )
    if not leaderboard:
        return ""

    rows = [
        [
            index,
            row.get("team_name", ""),
            "${:.0f}".format(num(row.get("amount"))),
        ]
        for index, row in enumerate(leaderboard, start=1)
    ]
    return section(
        "Challenge Payout Leaderboard",
        table(["Rank", "Team", "Winnings"], rows, True),
    )


def total_payouts(ctx):
    league_rows = (
        (ctx.get("postseason_data") or {}).get("league_payouts") or []
    )
    challenge_rows = (
        (ctx.get("challenge_data") or {}).get("payout_leaderboard") or []
    )

    league = {}
    challenges = {}
    teams = set()

    for row in league_rows:
        name = str(row.get("team_name") or "").strip()
        if name:
            teams.add(name)
            league[name] = league.get(name, 0.0) + num(row.get("amount"))

    for row in challenge_rows:
        name = str(row.get("team_name") or "").strip()
        if name:
            teams.add(name)
            challenges[name] = (
                challenges.get(name, 0.0) + num(row.get("amount"))
            )

    if not teams:
        return ""

    ordered = sorted(
        teams,
        key=lambda name: (
            -(league.get(name, 0.0) + challenges.get(name, 0.0)),
            -league.get(name, 0.0),
            name.lower(),
        ),
    )
    rows = [
        [
            name,
            "${:.0f}".format(league.get(name, 0.0)),
            "${:.0f}".format(challenges.get(name, 0.0)),
        ]
        for name in ordered
    ]
    rows.append([
        "TOTAL",
        "${:.0f}".format(sum(league.values())),
        "${:.0f}".format(sum(challenges.values())),
    ])

    return section(
        "Total Payouts",
        table(["Team", "League", "Challenges"], rows, True),
    )


def generic_postseason(ctx, key, title):
    value = (ctx.get("postseason_data") or {}).get(key)
    if not value:
        return ""
    if isinstance(value, str):
        return section(title, '<div class="callout">{}</div>'.format(escape(value)))
    if isinstance(value, dict):
        text = value.get("team_name") or value.get("winner_name") or value.get("champion") or value.get("summary")
        return section(title, highlight(title, text, value.get("detail", ""))) if text else ""
    return ""


def render(name, ctx):
    mapping = {
        "matchup_results": matchup_results,
        "weekly_highlights": weekly_highlights,
        "challenge_update": challenge_update,
        "challenge_results": challenge_results,
        "challenge_standings": challenge_standings,
        "challenge_standings_final": lambda c: challenge_standings(c, True),
        "challenge_leaderboard": challenge_leaderboard,
        "next_challenge": next_challenge,
        "standings": standings,
        "final_standings": lambda c: standings(c, True),
        "power_rankings": power_rankings,
        "power_rankings_final": lambda c: power_rankings(c, True),
        "beyond_box_score": beyond_box_score,
        "season_beyond_box_score": lambda c: beyond_box_score(c, True),
        "upcoming_matchups": upcoming_matchups,
        "league_admin": league_admin,
        "losers_trophy": losers_trophy,
        "playoff_preview": playoff_preview,
        "toilet_bowl_preview": toilet_bowl_preview,
        "playoff_results": playoff_results,
        "toilet_bowl": toilet_bowl,
        "toilet_bowl_winner": toilet_bowl_winner,
        "championship_matchup": championship_matchup,
        "next_round_matchups": next_round_matchups,
        "champion": league_champion,
        "final_playoff_results": playoff_results,
        "toilet_bowl_final": toilet_bowl,
        "final_season_results": lambda c: standings(c, True),
        "challenge_winners": challenge_winners,
        "challenge_payout_leaderboard": challenge_payout_leaderboard,
        "total_payouts": total_payouts,
        "season_accolades": season_accolades,
        "payout_summary": lambda c: generic_postseason(c, "payout_summary", "Payout Summary"),
    }
    return mapping[name](ctx)
