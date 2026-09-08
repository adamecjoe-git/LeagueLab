"""Outlook-friendly weekly LeagueLab newsletter renderer.

Uses the same data/context and newsletter layout decisions as the browser
newsletter, but renders with presentation tables and inline styles so Gmail
and desktop Outlook do not need CSS Grid/Flexbox support.

Python 3.8 compatible.
"""
from html import escape

from leaguelab.newsletter_blocks import (
    build_matchups,
    f,
    movement,
    num,
    pct,
    record,
)
from leaguelab.newsletter_layouts import blocks_for, newsletter_type_for_week


def _e(value):
    """Escape HTML and encode non-ASCII characters as numeric entities."""
    text = escape(str(value if value is not None else ""))
    return text.encode("ascii", "xmlcharrefreplace").decode("ascii")


def _section(title, body, subtitle=""):
    if not body:
        return ""
    subtitle_html = ""
    if subtitle:
        subtitle_html = (
            '<div style="margin:0 0 12px 0;color:#718694;font-size:12px;'
            'line-height:17px;">{}</div>'
        ).format(_e(subtitle))
    return (
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
        'style="width:100%;border-collapse:collapse;background:#fbfdff;'
        'mso-table-lspace:0pt;mso-table-rspace:0pt;">'
        '<tr><td align="left" style="padding:22px 28px;border-bottom:1px solid #dce8ef;'
        'font-family:Arial,Helvetica,sans-serif;color:#263746;text-align:left;">'
        '<div style="margin:0 0 12px 0;color:#34576e;font-size:19px;'
        'font-weight:bold;line-height:24px;">{}</div>{}{}</td></tr></table>'
    ).format(_e(title), subtitle_html, body)


def _table(headers, rows, widths=None, first_row_highlight=False):
    if not rows:
        return ""
    headers_html = []
    for idx, header in enumerate(headers):
        width_attr = ""
        if widths and idx < len(widths) and widths[idx]:
            width_attr = ' width="{}"'.format(widths[idx])
        headers_html.append(
            '<th{} align="left" style="padding:8px 7px;background:#eaf3f8;'
            'border-bottom:2px solid #bfd3df;font-family:Arial,Helvetica,sans-serif;'
            'font-size:12px;line-height:16px;color:#34576e;text-align:left;">{}</th>'.format(
                width_attr, _e(header)
            )
        )

    body_html = []
    for row_index, row in enumerate(rows):
        cells = []
        for idx, value in enumerate(row):
            width_attr = ""
            if widths and idx < len(widths) and widths[idx]:
                width_attr = ' width="{}"'.format(widths[idx])
            bg = "background:#f0f7fb;" if first_row_highlight and row_index == 0 else ""
            weight = "font-weight:bold;" if first_row_highlight and row_index == 0 else ""
            cells.append(
                '<td{} align="left" valign="top" style="padding:8px 7px;'
                'border-bottom:1px solid #dce8ef;{}{}font-family:Arial,Helvetica,sans-serif;'
                'font-size:12px;line-height:16px;color:#263746;text-align:left;">{}</td>'.format(
                    width_attr, bg, weight, value
                )
            )
        body_html.append("<tr>{}</tr>".format("".join(cells)))

    return (
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
        'style="width:100%;border-collapse:collapse;table-layout:fixed;'
        'mso-table-lspace:0pt;mso-table-rspace:0pt;">'
        '<thead><tr>{}</tr></thead><tbody>{}</tbody></table>'
    ).format("".join(headers_html), "".join(body_html))


def _card_table(cards, columns=2):
    """Fixed-column Outlook-safe card layout."""
    if not cards:
        return ""
    rows = []
    cell_width = int(100 / columns)
    for index in range(0, len(cards), columns):
        chunk = cards[index:index + columns]
        cells = []
        for card in chunk:
            cells.append(
                '<td width="{}%" valign="top" style="width:{}%;padding:5px;'
                'text-align:left;">{}</td>'.format(cell_width, cell_width, card)
            )
        while len(cells) < columns:
            cells.append(
                '<td width="{}%" style="width:{}%;padding:5px;">&nbsp;</td>'.format(
                    cell_width, cell_width
                )
            )
        rows.append("<tr>{}</tr>".format("".join(cells)))
    return (
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
        'style="width:100%;border-collapse:collapse;table-layout:fixed;'
        'mso-table-lspace:0pt;mso-table-rspace:0pt;">{}</table>'
    ).format("".join(rows))


def _highlight_card(label, value, detail="", column=0):
    """Outlook-safe highlight tile using the browser newsletter's 3-column palette."""
    palettes = (
        ("#f0f7fb", "#6f98b3"),
        ("#f2f1fa", "#8d8ab5"),
        ("#eef8f5", "#78a798"),
    )
    background, border = palettes[int(column) % 3]
    return (
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
        'style="width:100%;border-collapse:collapse;background:{};'
        'border-left:3px solid {};">'
        '<tr><td valign="top" style="padding:12px 13px;font-family:Arial,Helvetica,sans-serif;'
        'text-align:left;">'
        '<div style="font-size:9px;line-height:12px;text-transform:uppercase;'
        'letter-spacing:.5px;color:#6a8191;font-weight:bold;">{}</div>'
        '<div style="margin-top:5px;font-size:15px;line-height:19px;font-weight:bold;'
        'color:#263746;">{}</div>'
        '<div style="margin-top:5px;color:#6b7f8d;font-size:11px;line-height:15px;">{}</div>'
        '</td></tr></table>'
    ).format(background, border, _e(label), _e(value), _e(detail))


def _note(text):
    return (
        '<div style="margin-top:10px;color:#6c8190;font-family:Arial,Helvetica,sans-serif;'
        'font-size:11px;line-height:16px;">{}</div>'
    ).format(_e(text))


def _callout(text):
    return (
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
        'style="width:100%;border-collapse:collapse;background:#eaf4fa;">'
        '<tr><td style="padding:10px 12px;font-family:Arial,Helvetica,sans-serif;'
        'font-size:12px;line-height:17px;color:#263746;">{}</td></tr></table>'
    ).format(_e(text))


def _matchup_results(ctx):
    cards = []
    for item in ctx.get("matchups") or []:
        cards.append(
            '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
            'style="width:100%;border-collapse:collapse;border:1px solid #d3e3ed;background:#ffffff;">'
            '<tr><td style="padding:9px 11px;background:#f0f7fb;border-bottom:1px solid #e5eef3;'
            'font-family:Arial,Helvetica,sans-serif;font-size:13px;font-weight:bold;">{}</td>'
            '<td width="80" align="right" style="padding:9px 11px;background:#f0f7fb;'
            'border-bottom:1px solid #e5eef3;font-family:Arial,Helvetica,sans-serif;'
            'font-size:15px;font-weight:bold;">{}</td></tr>'
            '<tr><td style="padding:9px 11px;border-bottom:1px solid #e5eef3;'
            'font-family:Arial,Helvetica,sans-serif;font-size:13px;">{}</td>'
            '<td width="80" align="right" style="padding:9px 11px;border-bottom:1px solid #e5eef3;'
            'font-family:Arial,Helvetica,sans-serif;font-size:15px;font-weight:bold;">{}</td></tr>'
            '<tr><td colspan="2" style="padding:6px 11px;color:#718694;'
            'font-family:Arial,Helvetica,sans-serif;font-size:10px;text-transform:uppercase;">'
            'Margin: {} pts</td></tr></table>'.format(
                _e(item["winner"]), _e(f(item["winner_score"])),
                _e(item["loser"]), _e(f(item["loser_score"])), _e(f(item["margin"]))
            )
        )
    return _section("Matchup Results", _card_table(cards, 2))


def _weekly_highlights(ctx):
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

    rows = [
        (
            _highlight_card("High Score", high.get("team_name", "-"), "{} pts".format(f(high.get("score"))), 0) if high else "",
            _highlight_card("Biggest Blowout", "{} over {}".format(blow["winner"], blow["loser"]), "{} pt margin".format(f(blow["margin"])), 1) if blow else "",
            _highlight_card("Most Points Left on Bench", left.get("team_name", "-"), "{} points".format(f(left.get("points_left_on_bench"))), 2) if left else "",
        ),
        (
            _highlight_card("Low Score", low.get("team_name", "-"), "{} pts".format(f(low.get("score"))), 0) if low else "",
            _highlight_card("Closest Matchup", "{} over {}".format(close["winner"], close["loser"]), "{} pt margin".format(f(close["margin"])), 1) if close else "",
            _highlight_card("Biggest Lineup Miss", miss.get("team_name", "-"), "{} over {} (+{})".format(
                miss.get("biggest_bench_player", "-"), miss.get("replaced_starter", "-"),
                f(miss.get("decision_points_gained"))), 2) if miss else "",
        ),
        (
            _highlight_card("Top Individual Performance", starter.get("player_name", "-"),
                "{} pts - {}".format(f(starter.get("points")), starter.get("team_name", "")).rstrip(" -"), 0) if starter else "",
            _highlight_card("Best Lineup", best.get("team_name", "-"),
                "{}% efficient".format(f(best.get("lineup_efficiency"), 1)), 1) if best else "",
            _highlight_card("Top Bench Player", bench.get("player_name", "-"),
                "{} pts - {}".format(f(bench.get("points")), bench.get("team_name", "")).rstrip(" -"), 2) if bench else "",
        ),
    ]
    cards = [card for row in rows for card in row if card]
    return _section("Weekly Highlights", _card_table(cards, 3))

def _standings(ctx, final=False):
    rows = [[
        _e(r.get("standings_rank", "")),
        _e(r.get("team_name", "")),
        _e(record(r)),
        _e(f(r.get("points_for"))),
        _e(movement(r.get("standings_movement"))),
        _e(r.get("current_streak", "")),
    ] for r in ctx.get("weekly_rows", [])]
    return _section(
        "Final Regular-Season Standings" if final else "Standings",
        _table(["Rank", "Team", "Record", "PF", "Move", "Streak"], rows,
               ["8%", "38%", "13%", "14%", "12%", "15%"])
    )


def _power_rankings(ctx, final=False):
    rows = [[
        _e(r.get("power_rank", "")),
        _e(r.get("team_name", "")),
        _e(f(r.get("power_score"))),
        _e(f(r.get("season_points"))),
        _e(pct(r.get("all_play_win_pct"))),
        _e(f(r.get("recent_avg_points"))),
        _e(record(r)),
    ] for r in ctx.get("power", [])]
    body = _table(
        ["Rank", "Team", "Power", "PF", "All-Play", "Recent", "Record"],
        rows, ["7%", "31%", "11%", "12%", "13%", "13%", "13%"]
    )
    if body:
        body += _note("Formula: 30% season scoring - 25% all-play - 35% recent form - 10% record")
    return _section("Final Regular-Season Power Rankings" if final else "Power Rankings", body)


def _challenge_header(data):
    if not data:
        return ""
    body = _card_table([
        _highlight_card(
            "Challenge", data.get("name", "-"),
            "{} - ${} prize".format(data.get("weeks", ""), data.get("prize", 10))
        )
    ], 1)
    description = data.get("description") or ""
    if description:
        body += (
            '<div style="margin-top:10px;padding:10px 12px;background:#f7fbfd;'
            'border-left:3px solid #9bb8ca;font-family:Arial,Helvetica,sans-serif;'
            'color:#526b7b;font-size:12px;line-height:18px;">{}</div>'
        ).format(_e(description))
    return body


def _challenge_update(ctx, results=False):
    return _section("Challenge Results" if results else "Challenge Update",
                    _challenge_header(ctx.get("challenge_data")))


def _challenge_standings(ctx):
    data = ctx.get("challenge_data") or {}
    rows = [[_e(r.get("rank", "")), _e(r.get("team_name", "")), _e(r.get("value", ""))]
            for r in data.get("standings", [])]
    return _section(
        "Challenge Standings",
        _table(["Rank", "Team", "Score"], rows, ["12%", "58%", "30%"], first_row_highlight=True)
    )


def _challenge_leaderboard(ctx):
    week = int(ctx.get("week", 0))
    if week < 2 or week > 14 or week % 2 != 0:
        return ""
    data = ctx.get("challenge_data") or {}
    leaderboard = data.get("payout_leaderboard") or data.get("payouts") or []
    rows = []
    for index, row in enumerate(leaderboard):
        amount = float(row.get("amount", row.get("amount_won", row.get("payout", row.get("winnings", 0)))) or 0)
        rows.append([
            _e(row.get("rank", index + 1)),
            _e(row.get("team_name", row.get("team", ""))),
            _e(row.get("challenge_wins", row.get("wins", row.get("challenges_won", "")))),
            _e("${:.0f}".format(amount)),
        ])
    return _section(
        "Challenge Leaderboard",
        _table(["Rank", "Team", "Challenge Wins", "Winnings"], rows, ["10%", "50%", "20%", "20%"])
    )


def _next_challenge(ctx):
    week = int(ctx.get("week", 0))
    if week < 2 or week >= 14 or week % 2 != 0:
        return ""
    data = ctx.get("challenge_data") or {}
    nxt = data.get("next_challenge") or {}
    if not isinstance(nxt, dict) or not nxt:
        return ""
    body = _card_table([_highlight_card(
        "Up Next", nxt.get("name", "-"),
        "{} - ${} prize".format(nxt.get("weeks", ""), nxt.get("prize", 10))
    )], 1)
    if nxt.get("description"):
        body += (
            '<div style="margin-top:10px;padding:10px 12px;background:#f7fbfd;'
            'border-left:3px solid #9bb8ca;font-family:Arial,Helvetica,sans-serif;'
            'color:#526b7b;font-size:12px;line-height:18px;">{}</div>'
        ).format(_e(nxt["description"]))
    return _section("Next Challenge", body)


def _beyond_box_score(ctx, season=False):
    season_luck = ctx.get("luck") or []
    weekly_rows = ctx.get("all_play_week") or []
    sos = ctx.get("sos") or []
    cards = []

    if weekly_rows and not season:
        projected_rows = [r for r in weekly_rows if num(r.get("projected_points")) > 0]
        if projected_rows:
            best = max(projected_rows, key=lambda r: num(r.get("points")) - num(r.get("projected_points")))
            delta = num(best.get("points")) - num(best.get("projected_points"))
            cards.append(_highlight_card("This Week - Overachiever", best.get("team_name", "-"), "{:+.2f} vs projection".format(delta), 0))
        else:
            current_week = int(ctx.get("week", 0))
            prior_by_team = {}
            for row in ctx.get("all_weekly_rows") or []:
                if int(num(row.get("week"))) < current_week:
                    key = str(row.get("team_key") or "")
                    prior_by_team.setdefault(key, []).append(num(row.get("weekly_score")))
            candidates = []
            for row in weekly_rows:
                prior = prior_by_team.get(str(row.get("team_key") or "")) or []
                if prior:
                    avg = sum(prior) / len(prior)
                    candidates.append((num(row.get("points")) - avg, row))
            if candidates:
                delta, best = max(candidates, key=lambda x: x[0])
                cards.append(_highlight_card("This Week - Overachiever", best.get("team_name", "-"), "{:+.2f} vs entering avg".format(delta), 0))

        def weekly_luck(row):
            result = str(row.get("actual_result") or "").upper()
            actual = 1.0 if result == "W" else (0.5 if result == "T" else 0.0)
            return actual - num(row.get("expected_weekly_wins"))

        lucky = max(weekly_rows, key=weekly_luck)
        unlucky = min(weekly_rows, key=weekly_luck)
        cards.append(_highlight_card("This Week - Luckiest", lucky.get("team_name", "-"), "{:+.2f} win luck".format(weekly_luck(lucky)), 0))
        cards.append(_highlight_card("This Week - Unluckiest", unlucky.get("team_name", "-"), "{:+.2f} win luck".format(weekly_luck(unlucky)), 0))

    current = ctx.get("weekly_rows") or []
    if current:
        best_season = max(current, key=lambda r: num(r.get("all_play_win_pct")))
        worst_season = min(current, key=lambda r: num(r.get("all_play_win_pct")))
        cards.append(_highlight_card("Season - All-Play Leader", best_season.get("team_name", "-"), pct(best_season.get("all_play_win_pct")), 1))
        cards.append(_highlight_card("Season - All-Play Bottom", worst_season.get("team_name", "-"), pct(worst_season.get("all_play_win_pct")), 2))

    if season_luck:
        cards.append(_highlight_card("Season - Luckiest", season_luck[0].get("team_name", "-"), "{:+.2f} wins vs expected".format(num(season_luck[0].get("luck_wins"))), 1))
        cards.append(_highlight_card("Season - Unluckiest", season_luck[-1].get("team_name", "-"), "{:+.2f} wins vs expected".format(num(season_luck[-1].get("luck_wins"))), 1))

    if sos:
        cards.append(_highlight_card("Season - Toughest SOS", sos[0].get("team_name", "-"), "{} SOS - {} opp avg".format(pct(sos[0].get("strength_of_schedule")), f(sos[0].get("avg_opponent_score"))), 2))
        cards.append(_highlight_card("Season - Weakest SOS", sos[-1].get("team_name", "-"), "{} SOS - {} opp avg".format(pct(sos[-1].get("strength_of_schedule")), f(sos[-1].get("avg_opponent_score"))), 2))

    title = "Beyond the Box Score - Season Edition" if season else "Beyond the Box Score"
    if not season:
        blue = [c for c in cards if "#f0f7fb" in c]
        lavender = [c for c in cards if "#f2f1fa" in c]
        green = [c for c in cards if "#eef8f5" in c]
        ordered = []
        for i in range(max(len(blue), len(lavender), len(green))):
            for column_cards in (blue, lavender, green):
                if i < len(column_cards):
                    ordered.append(column_cards[i])
        cards = ordered
    body = _card_table(cards, 3)
    if body:
        body += _note("Weekly luck compares the matchup result with that week's all-play expectation. Season luck and SOS are through this newsletter week.")
    return _section(title, body)


def _upcoming_matchups(ctx, title="Next Week's Matchups"):
    data = ctx.get("upcoming_data") or {}
    matchups = data.get("matchups") or []
    cards = []
    for index, item in enumerate(matchups):
        a, b = item["team_a"], item["team_b"]
        badge = ""
        if index == data.get("matchup_to_watch"):
            badge = (
                '<div style="margin:0 0 7px 0;">'
                '<span style="display:inline-block;padding:3px 6px;background:#dcecf5;'
                'color:#456b83;border-radius:10px;font-family:Arial,Helvetica,sans-serif;'
                'font-size:9px;line-height:11px;font-weight:bold;text-transform:uppercase;'
                'white-space:nowrap;">MATCHUP TO WATCH</span></div>'
            )

        def team_line(team):
            rank = "#{}".format(team["power_rank"]) if team.get("power_rank") else "#-"
            projection = ""
            if team.get("projected_points") is not None and num(team.get("projected_points")) > 0:
                projection = ' <span style="color:#6f98b3;font-size:11px;">- Proj {}</span>'.format(
                    _e(f(team.get("projected_points")))
                )
            return "<strong>{} {}</strong> <span style='color:#6c8190;'>({})</span>{}".format(
                _e(rank), _e(team.get("team_name", "-")), _e(team.get("record", "")), projection
            )

        cards.append(
            '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
            'style="width:100%;border-collapse:collapse;background:#f4f9fc;border:1px solid #d3e3ed;">'
            '<tr><td style="padding:12px 13px;font-family:Arial,Helvetica,sans-serif;'
            'font-size:13px;line-height:18px;color:#263746;">{}{}'
            '<div style="padding:4px 0;color:#7d909c;font-size:10px;text-transform:uppercase;">vs</div>'
            '{}</td></tr></table>'.format(badge, team_line(a), team_line(b))
        )
    subtitle = "Week {} - Rank shown is LeagueLab Power Ranking".format(data.get("week", ""))
    return _section(title, _card_table(cards, 2), subtitle)


def _league_admin(ctx):
    data = ctx.get("admin_data") or {}
    if not data:
        return ""
    dues = data.get("dues") if isinstance(data.get("dues"), dict) else data
    pieces = []
    if dues and ("paid_count" in dues or "unpaid_count" in dues):
        cards = [
            _highlight_card("Dues Paid", "{} of {}".format(dues.get("paid_count", 0), dues.get("team_count", 0)),
                            "${:.0f} collected".format(num(dues.get("total_paid")))),
            _highlight_card("Outstanding", dues.get("unpaid_count", 0),
                            "${:.0f} remaining".format(num(dues.get("balance_due"))), 1),
        ]
        pieces.append(_card_table(cards, 2))
        owed = dues.get("unpaid") or dues.get("unpaid_teams") or dues.get("still_owed") or []
        if owed:
            bubbles = []
            for x in owed:
                bubbles.append(
                    '<td valign="top" style="padding:3px 4px 3px 0;">'
                    '<table role="presentation" cellspacing="0" cellpadding="0" border="0" '
                    'style="border-collapse:separate;background:#f2f1fa;border:1px solid #d8d5e8;'
                    'border-radius:16px;"><tr><td style="padding:6px 10px;'
                    'font-family:Arial,Helvetica,sans-serif;font-size:11px;line-height:14px;'
                    'color:#263746;white-space:nowrap;">{} &#8212; ${:.0f}</td></tr></table></td>'.format(
                        _e(x.get("team_name", "")),
                        num(x.get("balance_due", x.get("balance", 0))),
                    )
                )
            # Four bubbles per row matches the browser newsletter while
            # remaining email-safe without relying on flexbox.
            bubble_rows = []
            for i in range(0, len(bubbles), 4):
                cells = bubbles[i:i + 4]
                while len(cells) < 4:
                    cells.append('<td width="25%" style="padding:3px;">&nbsp;</td>')
                bubble_rows.append('<tr>{}</tr>'.format("".join(cells)))
            pieces.append(
                '<table role="presentation" cellspacing="0" cellpadding="0" border="0" '
                'style="margin-top:7px;border-collapse:collapse;">{}</table>'.format(
                    "".join(bubble_rows)
                )
            )
        elif dues.get("unpaid_count", 0) == 0:
            pieces.append('<div style="margin-top:10px;">{}</div>'.format(_callout("All league dues are paid.")))

    notes = data.get("notes") or data.get("items") or []
    if isinstance(notes, str):
        notes = [notes]
    if notes:
        items = "".join(
            '<li style="margin-bottom:4px;">{}</li>'.format(_e(item)) for item in notes
        )
        pieces.append(
            '<div style="margin-top:14px;font-size:14px;font-weight:bold;color:#45677d;">Commissioner Notes</div>'
            '<ul style="margin:8px 0 0 20px;padding:0;font-family:Arial,Helvetica,sans-serif;'
            'font-size:13px;line-height:20px;color:#263746;">{}</ul>'.format(items)
        )
    return _section("League Admin", "".join(pieces))


def _losers_trophy(ctx):
    rows = ctx.get("weekly_rows") or []
    if not rows:
        return ""
    loser = max(rows, key=lambda r: int(num(r.get("standings_rank"), 0)))
    return _section("Loser's Trophy", _card_table([
        _highlight_card("12th Place", loser.get("team_name", "-"), "Regular-season finish")
    ], 1))


def _next_round_cards(ctx):
    week = int(ctx.get("week", 0))
    data = ctx.get("postseason_data") or {}
    playoff = data.get("playoff") or {}
    toilet = data.get("toilet_bowl") or {}
    items = []

    if week == 14:
        items.extend((item, "Playoff Quarterfinal") for item in playoff.get("quarterfinals") or [])
        items.extend((item, "Toilet Bowl Semifinal") for item in toilet.get("preview") or [])
    elif week == 15:
        items.extend((item, "Playoff Semifinal") for item in playoff.get("championship_semifinals") or [])
        items.extend((item, "Consolation Semifinal") for item in playoff.get("consolation_semifinals") or [])
        t = toilet.get("championship") or {}
        if t:
            items.append(({
                "team_a": {"seed": t.get("team_a_seed"), "team_name": t.get("team_a_name"),
                           "projected_points": t.get("team_a_projected_points")},
                "team_b": {"seed": t.get("team_b_seed"), "team_name": t.get("team_b_name"),
                           "projected_points": t.get("team_b_projected_points")},
            }, "Toilet Bowl Final"))
    elif week == 16:
        finals = playoff.get("finals") or {}
        for key, label in (("championship", "Championship"), ("third_place", "3rd Place"),
                           ("fifth_place", "5th Place"), ("seventh_place", "7th Place")):
            if finals.get(key):
                items.append((finals[key], label))

    cards = []
    for item, label in items:
        a = item.get("team_a") or {}
        b = item.get("team_b") or {}
        if not a or not b:
            continue

        def line(team):
            proj = team.get("projected_points")
            p = " - Proj {}".format(f(proj)) if proj is not None and num(proj) > 0 else ""
            return "#{} {}{}".format(team.get("seed", "-"), team.get("team_name", "-"), p)

        cards.append(
            '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
            'style="width:100%;border-collapse:collapse;background:#f4f9fc;border:1px solid #d3e3ed;">'
            '<tr><td style="padding:12px 13px;font-family:Arial,Helvetica,sans-serif;font-size:13px;line-height:18px;">'
            '<div style="margin-bottom:5px;color:#4f7f9d;font-size:8px;font-weight:bold;'
            'text-transform:uppercase;">{}</div><strong>{}</strong>'
            '<div style="padding:4px 0;color:#7d909c;font-size:10px;text-transform:uppercase;">vs</div>'
            '<strong>{}</strong></td></tr></table>'.format(_e(label), _e(line(a)), _e(line(b)))
        )
    return _section(
        "Next Round Matchups", _card_table(cards, 2),
        "Week {} - Final regular-season seeds shown".format(week + 1)
    )


def _bracket_matchup_card(item, label):
    def team_row(team, winner_key):
        if not team:
            return (
                '<tr><td colspan="3" style="padding:8px;background:#ffffff;color:#9aabb5;'
                'font-family:Arial,Helvetica,sans-serif;font-size:11px;font-style:italic;">TBD</td></tr>'
            )
        winner = winner_key and str(team.get("team_key") or "") == str(winner_key)
        complete = bool(winner_key)
        bg = "#e8f3f8" if winner else "#ffffff"
        weight = "font-weight:bold;" if winner else ""
        deco = "text-decoration:line-through;color:#8a9ba6;" if complete and not winner else ""
        score = team.get("score")
        proj = team.get("projected_points")
        value = f(score) if score is not None else ("Proj {}".format(f(proj)) if proj is not None and num(proj) > 0 else "")
        return (
            '<tr><td width="34" style="padding:8px;background:{};font-family:Arial,Helvetica,sans-serif;'
            'font-size:10px;color:#7c919f;{}">#{}</td>'
            '<td style="padding:8px;background:{};font-family:Arial,Helvetica,sans-serif;'
            'font-size:11px;{}{}">{}</td>'
            '<td width="70" align="right" style="padding:8px;background:{};'
            'font-family:Arial,Helvetica,sans-serif;font-size:11px;{}">{}</td></tr>'
        ).format(
            bg, weight, _e(team.get("seed", "-")), bg, weight, deco,
            _e(team.get("team_name", "-")), bg, weight, _e(value)
        )

    winner_key = (item or {}).get("winner_key")
    return (
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
        'style="width:100%;border-collapse:collapse;border:1px solid #cbdde7;background:#ffffff;">'
        '<tr><td colspan="3" align="center" style="padding:6px 8px;background:#263746;color:#ffffff;'
        'font-family:Arial,Helvetica,sans-serif;font-size:10px;font-weight:bold;'
        'text-transform:uppercase;">{}</td></tr>{}{}</table>'
    ).format(
        _e(label),
        team_row((item or {}).get("team_a"), winner_key),
        team_row((item or {}).get("team_b"), winner_key),
    )


def _playoff_bracket(ctx, title, preview=False):
    """Email-safe horizontal bracket matching the browser's round alignment."""
    playoff = (ctx.get("postseason_data") or {}).get("playoff") or {}
    if not playoff:
        return ""

    qfs = playoff.get("quarterfinals") or []
    semis = playoff.get("championship_semifinals") or []
    consolation = playoff.get("consolation_semifinals") or []
    finals = playoff.get("finals") or {}

    qf_cards = [
        _bracket_matchup_card(qfs[i] if i < len(qfs) else None, "Quarterfinal")
        for i in range(4)
    ]
    sf_cards = [
        _bracket_matchup_card(semis[i] if i < len(semis) else None, "Semifinal")
        for i in range(2)
    ]
    final_cards = [
        _bracket_matchup_card(finals.get("championship"), "Final"),
        _bracket_matchup_card(finals.get("third_place"), "3rd Place"),
    ]

    # Four logical rows let each semifinal sit between its two source
    # quarterfinals, while the Final / 3rd Place cards occupy the same
    # two-row bands. This reproduces the browser bracket relationship
    # without flex/grid CSS, which is unreliable in email clients.
    championship = (
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
        'style="width:100%;table-layout:fixed;border-collapse:collapse;">'
        '<tr>'
        '<td width="31%" valign="middle" style="padding:5px 10px 5px 0;">{}</td>'
        '<td width="34%" rowspan="2" valign="middle" style="padding:5px 10px;">{}</td>'
        '<td width="35%" rowspan="2" valign="middle" style="padding:5px 0 5px 10px;">{}</td>'
        '</tr>'
        '<tr><td valign="middle" style="padding:5px 10px 5px 0;">{}</td></tr>'
        '<tr>'
        '<td valign="middle" style="padding:5px 10px 5px 0;">{}</td>'
        '<td rowspan="2" valign="middle" style="padding:5px 10px;">{}</td>'
        '<td rowspan="2" valign="middle" style="padding:5px 0 5px 10px;">{}</td>'
        '</tr>'
        '<tr><td valign="middle" style="padding:5px 10px 5px 0;">{}</td></tr>'
        '</table>'
    ).format(
        qf_cards[0], sf_cards[0], final_cards[0],
        qf_cards[1],
        qf_cards[2], sf_cards[1], final_cards[1],
        qf_cards[3],
    )

    consolation_cards = [
        _bracket_matchup_card(
            consolation[i] if i < len(consolation) else None,
            "Consolation Semifinal",
        )
        for i in range(2)
    ]
    placement_cards = [
        _bracket_matchup_card(finals.get("fifth_place"), "5th Place"),
        _bracket_matchup_card(finals.get("seventh_place"), "7th Place"),
    ]

    source_note = (
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
        'style="width:100%;border-collapse:collapse;border:1px dashed #c8d8e2;">'
        '<tr><td align="center" style="padding:12px;font-family:Arial,Helvetica,sans-serif;'
        'font-size:11px;line-height:15px;color:#7b909e;">Quarterfinal losers</td></tr>'
        '</table>'
    )

    consolation_html = (
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
        'style="width:100%;table-layout:fixed;border-collapse:collapse;">'
        '<tr>'
        '<td width="20%" rowspan="2" valign="middle" style="padding:5px 10px 5px 0;">{}</td>'
        '<td width="40%" valign="middle" style="padding:5px 10px;">{}</td>'
        '<td width="40%" valign="middle" style="padding:5px 0 5px 10px;">{}</td>'
        '</tr>'
        '<tr>'
        '<td valign="middle" style="padding:5px 10px;">{}</td>'
        '<td valign="middle" style="padding:5px 0 5px 10px;">{}</td>'
        '</tr>'
        '</table>'
    ).format(
        source_note,
        consolation_cards[0], placement_cards[0],
        consolation_cards[1], placement_cards[1],
    )

    body = (
        '<div style="margin-bottom:8px;color:#45677d;font-family:Arial,Helvetica,sans-serif;'
        'font-size:13px;line-height:16px;font-weight:bold;text-transform:uppercase;'
        'letter-spacing:.6px;">Championship Bracket</div>'
        + championship
        + '<div style="margin:22px 0 8px;color:#45677d;font-family:Arial,Helvetica,sans-serif;'
          'font-size:13px;line-height:16px;font-weight:bold;text-transform:uppercase;'
          'letter-spacing:.6px;">Consolation / Placement Bracket</div>'
        + consolation_html
    )

    subtitle = "Seeds are final regular-season standings."
    if not preview:
        subtitle += " Completed matchup winners are highlighted."
    return _section(title, body, subtitle)

def _toilet_item(item):
    if not item:
        return None
    if "team_a" in item:
        return item
    return {
        "team_a": {
            "seed": item.get("team_a_seed"), "team_key": item.get("team_a_key"),
            "team_name": item.get("team_a_name"), "score": item.get("team_a_score"),
            "projected_points": item.get("team_a_projected_points"),
        },
        "team_b": {
            "seed": item.get("team_b_seed"), "team_key": item.get("team_b_key"),
            "team_name": item.get("team_b_name"), "score": item.get("team_b_score"),
            "projected_points": item.get("team_b_projected_points"),
        },
        "winner_key": item.get("winner_key"),
    }


def _toilet_bowl(ctx, title, preview=False):
    data = (ctx.get("postseason_data") or {}).get("toilet_bowl") or {}
    if not data:
        return ""

    semis = data.get("semifinals") or []
    if not semis:
        semis = data.get("preview") or []

    semi_cards = [
        _bracket_matchup_card(
            _toilet_item(semis[i]) if i < len(semis) else None,
            "Semifinal",
        )
        for i in range(2)
    ]
    final_card = _bracket_matchup_card(
        _toilet_item(data.get("championship")),
        "Final",
    )

    # Two semifinal rows feeding a vertically centered Final.
    body = (
        '<div style="margin-bottom:8px;color:#45677d;font-family:Arial,Helvetica,sans-serif;'
        'font-size:13px;line-height:16px;font-weight:bold;text-transform:uppercase;'
        'letter-spacing:.6px;">Toilet Bowl</div>'
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
        'style="width:100%;table-layout:fixed;border-collapse:collapse;">'
        '<tr>'
        '<td width="50%" valign="middle" style="padding:5px 14px 5px 0;">{}</td>'
        '<td width="50%" rowspan="2" valign="middle" style="padding:5px 0 5px 14px;">{}</td>'
        '</tr>'
        '<tr><td valign="middle" style="padding:5px 14px 5px 0;">{}</td></tr>'
        '</table>'
    ).format(semi_cards[0], final_card, semi_cards[1])

    subtitle = "Seeds are final regular-season standings."
    if not preview:
        subtitle += " Completed matchup winners are highlighted."
    return _section(title, body, subtitle)

def _champion(ctx):
    champion = ((ctx.get("postseason_data") or {}).get("playoff") or {}).get("champion") or {}
    if not champion:
        return ""
    body = (
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
        'style="width:100%;border-collapse:collapse;background:#e8f3f8;border:1px solid #bdd4e1;">'
        '<tr><td align="center" style="padding:18px 20px;font-family:Arial,Helvetica,sans-serif;">'
        '<div style="font-size:52px;line-height:56px;margin-bottom:8px;">&#127942;</div>'
        '<div style="font-size:10px;text-transform:uppercase;letter-spacing:1px;'
        'color:#5d7889;font-weight:bold;">League Champion</div>'
        '<div style="margin-top:5px;font-size:22px;font-weight:bold;color:#294b60;">#{} {}</div>'
        '</td></tr></table>'
    ).format(_e(champion.get("seed", "-")), _e(champion.get("team_name", "-")))
    return _section("League Champion", body)


def _toilet_bowl_winner(ctx):
    champion = ((ctx.get("postseason_data") or {}).get("toilet_bowl") or {}).get("champion") or {}
    if not champion:
        return ""
    body = (
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
        'style="width:100%;border-collapse:collapse;background:#e8f3f8;border:1px solid #bdd4e1;">'
        '<tr><td align="center" style="padding:18px 20px;font-family:Arial,Helvetica,sans-serif;">'
        '<div style="font-size:52px;line-height:56px;margin-bottom:8px;">&#128701;</div>'
        '<div style="font-size:10px;text-transform:uppercase;letter-spacing:1px;'
        'color:#5d7889;font-weight:bold;">Toilet Bowl Champion</div>'
        '<div style="margin-top:5px;font-size:22px;font-weight:bold;color:#294b60;">#{} {}</div>'
        '<div style="margin-top:5px;color:#647e8e;font-size:12px;">${:.0f} payout</div>'
        '</td></tr></table>'
    ).format(_e(champion.get("seed", "-")), _e(champion.get("team_name", "-")), num(champion.get("payout")))
    return _section("Toilet Bowl Champion", body)


def _challenge_winners(ctx):
    winners = (ctx.get("challenge_data") or {}).get("challenge_winners", [])
    rows = [[_e(r.get("name", "")), _e(r.get("team_name", "")), _e("${:.0f}".format(num(r.get("prize"))))]
            for r in winners]
    return _section("Challenge Winners", _table(["Challenge", "Winner", "Prize"], rows, ["45%", "40%", "15%"]))


def _money_num(value, default=0.0):
    """Parse numeric or formatted money values such as 10, '10', '$10', '$10.00'."""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return default
    text = text.replace("$", "").replace(",", "").strip()
    try:
        return float(text)
    except (TypeError, ValueError):
        return default


def _challenge_payout_amount(row):
    """Return challenge winnings across historical/current newsletter schemas."""
    if not isinstance(row, dict):
        return 0.0
    return _money_num(
        row.get(
            "amount",
            row.get(
                "amount_won",
                row.get("payout", row.get("winnings", 0)),
            ),
        )
    )


def _challenge_payout_rows(data):
    """Return reliable final challenge payout rows."""
    data = data or {}
    leaderboard = data.get("payout_leaderboard") or data.get("payouts") or []
    if leaderboard and sum(_challenge_payout_amount(row) for row in leaderboard) > 0:
        return leaderboard

    totals = {}
    for row in data.get("challenge_winners") or []:
        name = str(row.get("team_name") or row.get("team") or "").strip()
        if not name:
            continue
        amount = _money_num(
            row.get(
                "prize",
                row.get(
                    "amount",
                    row.get(
                        "amount_won",
                        row.get("payout", row.get("winnings", 0)),
                    ),
                ),
            )
        )
        totals[name] = totals.get(name, 0.0) + amount

    return [
        {"team_name": name, "amount": amount}
        for name, amount in sorted(
            totals.items(),
            key=lambda item: (-item[1], item[0].lower()),
        )
    ]


def _challenge_payout_leaderboard(ctx):
    rows_in = (ctx.get("challenge_data") or {}).get("payout_leaderboard", [])
    rows = [[_e(i), _e(r.get("team_name", "")), _e("${:.0f}".format(_challenge_payout_amount(r)))]
            for i, r in enumerate(rows_in, 1)]
    return _section("Challenge Payout Leaderboard", _table(["Rank", "Team", "Winnings"], rows, ["10%", "70%", "20%"]))


def _total_payouts(ctx):
    league_rows = (ctx.get("postseason_data") or {}).get("league_payouts") or []
    challenge_rows = _challenge_payout_rows(ctx.get("challenge_data"))
    league, challenges, teams = {}, {}, set()
    for row in league_rows:
        name = str(row.get("team_name") or "").strip()
        if name:
            teams.add(name)
            league[name] = league.get(name, 0.0) + num(row.get("amount"))
    for row in challenge_rows:
        name = str(row.get("team_name") or "").strip()
        if name:
            teams.add(name)
            challenges[name] = challenges.get(name, 0.0) + _challenge_payout_amount(row)
    ordered = sorted(teams, key=lambda n: (-(league.get(n, 0) + challenges.get(n, 0)), -league.get(n, 0), n.lower()))
    rows = [[_e(name), _e("${:.0f}".format(league.get(name, 0))), _e("${:.0f}".format(challenges.get(name, 0)))]
            for name in ordered]
    if rows:
        rows.append(["<strong>TOTAL</strong>",
                     "<strong>{}</strong>".format(_e("${:.0f}".format(sum(league.values())))),
                     "<strong>{}</strong>".format(_e("${:.0f}".format(sum(challenges.values()))))])
    return _section("Total Payouts", _table(["Team", "League", "Challenges"], rows, ["60%", "20%", "20%"]))


def _season_accolades(ctx):
    if int(ctx.get("week", 0)) < 17:
        return ""
    try:
        from leaguelab.season_accolades import build_season_accolades
        awards = build_season_accolades(ctx.get("season"))
    except (ImportError, OSError, ValueError):
        awards = []
    cards = []
    for index, award in enumerate(awards):
        icon = _e(award.get("icon", ""))
        title = _e(award.get("title", ""))
        winner = _e(award.get("winner", "-"))
        detail = _e(award.get("detail", ""))
        palettes = (
            ("#f0f7fb", "#6f98b3"),
            ("#f2f1fa", "#8d8ab5"),
            ("#eef8f5", "#78a798"),
        )
        background, border = palettes[index % 3]
        cards.append(
            '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
            'style="width:100%;border-collapse:collapse;background:{};border-left:3px solid {};">'
            '<tr><td valign="top" style="padding:14px 15px;font-family:Arial,Helvetica,sans-serif;">'
            '<div style="font-size:24px;line-height:28px;">{}</div>'
            '<div style="margin-top:7px;font-size:10px;line-height:13px;text-transform:uppercase;'
            'letter-spacing:.7px;color:#6a8191;font-weight:bold;">{}</div>'
            '<div style="margin-top:6px;font-size:16px;line-height:20px;font-weight:bold;'
            'color:#34576e;">{}</div>'
            '<div style="margin-top:5px;color:#6b7f8d;font-size:12px;line-height:16px;">{}</div>'
            '</td></tr></table>'.format(background, border, icon, title, winner, detail)
        )
    return _section("Season Accolades", _card_table(cards, 3))


def _generic_postseason(ctx, key, title):
    value = (ctx.get("postseason_data") or {}).get(key)
    if not value:
        return ""
    if isinstance(value, str):
        return _section(title, _callout(value))
    if isinstance(value, dict):
        text = value.get("team_name") or value.get("winner_name") or value.get("champion") or value.get("summary")
        if text:
            return _section(title, _card_table([_highlight_card(title, text, value.get("detail", ""))], 1))
    return ""


def _render(name, ctx):
    mapping = {
        "matchup_results": _matchup_results,
        "weekly_highlights": _weekly_highlights,
        "challenge_update": _challenge_update,
        "challenge_results": lambda c: _challenge_update(c, True),
        "challenge_standings": _challenge_standings,
        "challenge_standings_final": _challenge_standings,
        "challenge_leaderboard": _challenge_leaderboard,
        "next_challenge": _next_challenge,
        "standings": _standings,
        "final_standings": lambda c: _standings(c, True),
        "power_rankings": _power_rankings,
        "power_rankings_final": lambda c: _power_rankings(c, True),
        "beyond_box_score": _beyond_box_score,
        "season_beyond_box_score": lambda c: _beyond_box_score(c, True),
        "upcoming_matchups": _upcoming_matchups,
        "league_admin": _league_admin,
        "losers_trophy": _losers_trophy,
        "playoff_preview": lambda c: _playoff_bracket(c, "Playoff Bracket / Preview", True),
        "toilet_bowl_preview": lambda c: _toilet_bowl(c, "Toilet Bowl Bracket / Preview", True),
        "playoff_results": lambda c: _playoff_bracket(c, "Playoff Bracket", False),
        "toilet_bowl": lambda c: _toilet_bowl(c, "Toilet Bowl Bracket", False),
        "toilet_bowl_winner": _toilet_bowl_winner,
        "championship_matchup": lambda c: _upcoming_matchups(c, "Championship Matchup"),
        "next_round_matchups": _next_round_cards,
        "champion": _champion,
        "final_playoff_results": lambda c: _playoff_bracket(c, "Playoff Bracket", False),
        "toilet_bowl_final": lambda c: _toilet_bowl(c, "Toilet Bowl Bracket", False),
        "final_season_results": lambda c: _standings(c, True),
        "challenge_winners": _challenge_winners,
        "challenge_payout_leaderboard": _challenge_payout_leaderboard,
        "total_payouts": _total_payouts,
        "season_accolades": _season_accolades,
        "payout_summary": lambda c: _generic_postseason(c, "payout_summary", "Payout Summary"),
    }
    renderer = mapping.get(name)
    return renderer(ctx) if renderer else ""


def build_weekly_email_html(
    season,
    week,
    analytics_result,
    league_name="XTreme Football",
    challenge_data=None,
    admin_data=None,
    upcoming_data=None,
    postseason_data=None,
    newsletter_type=None,
    regular_season_end=14,
    season_end=17,
):
    """Build fixed-width Outlook-friendly weekly newsletter HTML."""
    ntype = newsletter_type_for_week(
        week, regular_season_end, season_end, newsletter_type
    )
    glance = analytics_result.get("week_at_a_glance") or {}
    weekly = [
        r for r in analytics_result.get("weekly_analytics", [])
        if int(num(r.get("week"))) == int(week)
    ]
    weekly.sort(key=lambda r: int(num(r.get("standings_rank"), 999)))

    ctx = {
        "season": season,
        "week": week,
        "glance": glance,
        "matchups": build_matchups(glance),
        "lineup_summary": analytics_result.get("lineup_summary") or {},
        "weekly_rows": weekly,
        "all_weekly_rows": analytics_result.get("weekly_analytics", []),
        "power": sorted(
            analytics_result.get("power_rankings", []),
            key=lambda r: int(num(r.get("power_rank"), 999)),
        ),
        "luck": sorted(
            analytics_result.get("luck", []),
            key=lambda r: num(r.get("luck_wins")),
            reverse=True,
        ),
        "sos": sorted(
            analytics_result.get("schedule_strength", []),
            key=lambda r: int(num(r.get("sos_rank"), 999)),
        ),
        "challenge_data": challenge_data,
        "admin_data": admin_data,
        "upcoming_data": upcoming_data,
        "postseason_data": postseason_data,
        "all_play_week": [
            r for r in analytics_result.get("all_play", [])
            if int(num(r.get("week"))) == int(week)
        ],
    }

    labels = {
        "regular_season": "Regular Season",
        "regular_season_final": "Regular Season Finale",
        "playoffs": "Playoffs",
        "championship": "Championship Week",
        "postseason_wrap": "Season Wrap-Up",
    }

    content = "".join(_render(name, ctx) for name in blocks_for(ntype))

    # Keep the same 900px canvas that proved reliable in the preseason email.
    return (
        '<!doctype html><html><head>'
        '<meta http-equiv="Content-Type" content="text/html; charset=utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>LeagueLab Week {}</title></head>'
        '<body style="margin:0;padding:0;background:#edf4f8;">'
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
        'bgcolor="#edf4f8" style="width:100%;border-collapse:collapse;'
        'mso-table-lspace:0pt;mso-table-rspace:0pt;">'
        '<tr><td align="center" valign="top" style="padding:0;">'
        '<table role="presentation" width="900" cellspacing="0" cellpadding="0" border="0" '
        'align="center" style="width:900px;border-collapse:collapse;background:#fbfdff;'
        'mso-table-lspace:0pt;mso-table-rspace:0pt;">'
        '<tr><td align="left" bgcolor="#567b95" style="padding:30px 28px;'
        'font-family:Arial,Helvetica,sans-serif;color:#ffffff;text-align:left;">'
        '<div style="margin:0;font-size:28px;line-height:34px;font-weight:bold;">{}</div>'
        '<div style="margin-top:7px;color:#e6eef3;font-size:13px;line-height:18px;">'
        'LeagueLab &#8226; {} &#8226; Week {} &#8226; {}</div></td></tr>'
        '<tr><td align="left" style="padding:0;text-align:left;">{}</td></tr>'
        '<tr><td align="center" style="padding:20px 28px;font-family:Arial,Helvetica,sans-serif;'
        'text-align:center;color:#8a9ba6;font-size:10px;">Generated by LeagueLab</td></tr>'
        '</table></td></tr></table></body></html>'
    ).format(
        _e(week), _e(league_name), _e(season), _e(week), _e(labels[ntype]), content
    )
