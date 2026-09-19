"""Outlook-friendly weekly LeagueLab newsletter renderer.

Uses the same data/context and newsletter layout decisions as the browser
newsletter, but renders with presentation tables and inline styles so Gmail
and desktop Outlook do not need CSS Grid/Flexbox support.

Python 3.8 compatible.
"""
from html import escape

from leaguelab.newsletter_layouts import blocks_for, newsletter_type_for_week


import re


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


def build_matchups(glance):
    rankings = (glance or {}).get("weekly_rankings", [])
    by_name = {
        str(row.get("team_name", "")): row
        for row in rankings
        if row.get("team_name")
    }
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
        opponent_score = row.get("opponent_points")
        if opponent_score is None or str(opponent_score).strip() == "":
            opponent_score = by_name.get(opponent, {}).get("score")
        opponent_score = num(opponent_score)

        if team_score >= opponent_score:
            winner, winner_score = team, team_score
            loser, loser_score = opponent, opponent_score
        else:
            winner, winner_score = opponent, opponent_score
            loser, loser_score = team, team_score

        output.append({
            "winner": winner,
            "winner_score": winner_score,
            "loser": loser,
            "loser_score": loser_score,
            "margin": abs(winner_score - loser_score),
        })

    output.sort(key=lambda item: item["winner_score"], reverse=True)
    return output


def _e(value):
    """Escape HTML and encode non-ASCII characters as numeric entities."""
    text = escape(str(value if value is not None else ""))
    return text.encode("ascii", "xmlcharrefreplace").decode("ascii")


def _section(title, body, subtitle=""):
    if not body:
        return ""
    subtitle_html = ""
    if subtitle:
        subtitle_html = ('<div style="margin:2px 0 14px 0;color:#697781;font-size:11px;line-height:16px;letter-spacing:.2px;">{}</div>').format(_e(subtitle))
    return (
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="width:100%;border-collapse:collapse;background:#FFFFFF;">'
        '<tr><td align="left" style="padding:26px 34px 28px;border-bottom:1px solid #DCE1E4;font-family:Arial,Helvetica,sans-serif;color:#20272C;text-align:left;">'
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="border-collapse:collapse;"><tr>'
        '<td valign="bottom"><div style="margin:0;color:#112B3E;font-family:Arial Black,Arial,Helvetica,sans-serif;font-size:22px;font-weight:900;line-height:27px;text-transform:uppercase;letter-spacing:-.3px;">{}</div>'
        '<div style="width:48px;height:4px;line-height:4px;background:#C58A2A;margin:8px 0 0 0;">&nbsp;</div></td>'
        '</tr></table>{}{}</td></tr></table>'
    ).format(_e(title), subtitle_html, body)

def _table(headers, rows, widths=None, first_row_highlight=False, alignments=None):
    if not rows:
        return ""
    headers_html = []
    for idx, header in enumerate(headers):
        width_attr = ""
        if widths and idx < len(widths) and widths[idx]:
            width_attr = ' width="{}"'.format(widths[idx])
        align = alignments[idx] if alignments and idx < len(alignments) else "left"
        headers_html.append(
            '<th{} align="{}" style="padding:8px 7px;background:#E7ECEF;'
            'border-bottom:2px solid #AEB8BF;font-family:Arial,Helvetica,sans-serif;'
            'font-size:11px;line-height:16px;color:#112B3E;text-align:{};text-transform:uppercase;letter-spacing:.5px;font-weight:bold;">{}</th>'.format(
                width_attr, align, align, _e(header)
            )
        )

    body_html = []
    for row_index, row in enumerate(rows):
        cells = []
        for idx, value in enumerate(row):
            width_attr = ""
            if widths and idx < len(widths) and widths[idx]:
                width_attr = ' width="{}"'.format(widths[idx])
            bg = "background:#F4EBDD;" if first_row_highlight and row_index == 0 else ""
            weight = "font-weight:bold;" if first_row_highlight and row_index == 0 else ""
            if idx == 1:
                weight += "font-weight:bold;"
            align = alignments[idx] if alignments and idx < len(alignments) else "left"
            cells.append(
                '<td{} align="{}" valign="top" style="padding:8px 7px;'
                'border-bottom:1px solid #D8DEE3;{}{}font-family:Arial,Helvetica,sans-serif;'
                'font-size:13px;line-height:17px;color:#222A30;text-align:{};">{}</td>'.format(
                    width_attr, align, bg, weight, align, value
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
    """Equal-height editorial tile where the statistic itself is the visual."""
    accent = ("#C58A2A", "#112B3E", "#71808A")[int(column) % 3]
    detail_text = str(detail or "")
    match = re.match(r"^([+-]?[0-9][0-9,.]*%?)(?:\s+(?:pts?|points?|SOS|wins?))?(?:\s*-\s*(.*)|\s+(vs\s+.*))?$", detail_text, re.I)
    stat = ""
    secondary = detail_text
    if match:
        stat = match.group(1)
        secondary = (match.group(2) or match.group(3) or "").strip()
        if secondary.lower().startswith("vs "):
            secondary = ""
    else:
        lead = re.match(r"^([+-]?[0-9][0-9,.]*%?)\b", detail_text)
        if lead:
            stat = lead.group(1)
            secondary = detail_text[lead.end():].strip(" -")
    if not stat:
        stat = {
            "Biggest Blowout": "MARGIN", "Closest Matchup": "CLOSE",
            "Biggest Lineup Miss": "MISS", "Challenge": "HOT",
            "Up Next": "NEXT", "Dues Paid": "PAID", "Outstanding": "DUE",
        }.get(str(label), "STAT")
    # Lineup efficiency cards are percentage metrics. Keep the % on the
    # large measure and do not repeat "efficient" beneath the team name.
    if str(label) in {"Most Efficient Lineup", "Least Efficient Lineup"}:
        if stat and not stat.endswith("%"):
            stat += "%"
        if secondary.lower() == "efficient":
            secondary = ""
    stat_color = "#A66D12" if str(label) == "High Score" else accent
    secondary_html = ''
    if secondary:
        secondary_html = '<div style="margin-top:5px;color:#60717C;font-size:12px;line-height:16px;">{}</div>'.format(_e(secondary))
    return (
        '<table role="presentation" width="100%" height="118" cellspacing="0" cellpadding="0" border="0" '
        'style="width:100%;height:118px;border-collapse:collapse;background:#F7F8F8;border:1px solid #DCE1E4;">'
        '<tr><td width="78" height="118" align="center" valign="middle" style="width:78px;height:118px;padding:0 7px;background:#F0F2F3;border-right:1px solid #DCE1E4;">'
        '<div style="font-family:Arial Black,Arial,sans-serif;font-size:21px;line-height:24px;font-weight:900;color:{};letter-spacing:-.4px;">{}</div>'
        '</td><td height="118" valign="middle" style="height:118px;padding:12px 12px;font-family:Arial,Helvetica,sans-serif;text-align:left;">'
        '<div style="font-size:12px;line-height:15px;text-transform:uppercase;letter-spacing:.8px;color:#60717C;font-weight:bold;">{}</div>'
        '<div style="margin-top:5px;font-family:Arial Black,Arial,Helvetica,sans-serif;font-size:17px;line-height:21px;font-weight:900;color:#112B3E;">{}</div>'
        '{}'
        '</td></tr></table>'
    ).format(stat_color, _e(stat), _e(label), _e(value), secondary_html)

def _note(text):
    return (
        '<div style="margin-top:10px;color:#66727C;font-family:Arial,Helvetica,sans-serif;'
        'font-size:11px;line-height:16px;">{}</div>'
    ).format(_e(text))


def _callout(text):
    return (
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
        'style="width:100%;border-collapse:collapse;background:#F5F1E8;">'
        '<tr><td style="padding:10px 12px;font-family:Arial,Helvetica,sans-serif;'
        'font-size:12px;line-height:17px;color:#222A30;">{}</td></tr></table>'
    ).format(_e(text))


def _matchup_results(ctx):
    cards = []
    weekly = ctx.get("weekly_rows") or []
    weekly_by_name = {str(r.get("team_name") or ""): r for r in weekly}
    ap_by_name = {str(r.get("team_name") or ""): r for r in (ctx.get("all_play_week") or [])}
    matchups = ctx.get("matchups") or []
    glance = ctx.get("glance") or {}

    high_name = str((glance.get("highest_team_score") or {}).get("team_name") or "")
    low_name = str((glance.get("lowest_team_score") or {}).get("team_name") or "")
    close = min(matchups, key=lambda x: num(x.get("margin"))) if matchups else None
    blow = max(matchups, key=lambda x: num(x.get("margin"))) if matchups else None

    # Biggest Upset: actual winner was a Yahoo-projected underdog.
    upset = None
    upset_gap = 0.0
    for item in matchups:
        winner_row = weekly_by_name.get(str(item.get("winner") or ""), {})
        loser_row = weekly_by_name.get(str(item.get("loser") or ""), {})
        winner_proj = num(winner_row.get("projected_points"))
        loser_proj = num(loser_row.get("projected_points"))
        if winner_proj > 0 and loser_proj > 0 and winner_proj < loser_proj:
            gap = loser_proj - winner_proj
            if gap > upset_gap:
                upset_gap = gap
                upset = item

    def wlt(row, prefix="actual"):
        if not row:
            return "0–0–0"
        return "{}–{}–{}".format(
            int(num(row.get(prefix + "_wins"))),
            int(num(row.get(prefix + "_losses"))),
            int(num(row.get(prefix + "_ties"))),
        )

    def ordinal(value):
        n = int(num(value))
        if 10 <= (n % 100) <= 20:
            suffix = "TH"
        else:
            suffix = {1: "ST", 2: "ND", 3: "RD"}.get(n % 10, "TH")
        return "{}{}".format(n, suffix) if n else ""

    def all_play_text(name):
        row = ap_by_name.get(str(name), {})
        return wlt(row, "all_play") if row else ""

    def all_play_rank(name):
        row = ap_by_name.get(str(name), {})
        return ordinal(row.get("weekly_rank")) if row else ""

    def team_badges(item, name):
        labels = []
        if name == high_name:
            labels.append("HIGH SCORE")
        if name == low_name:
            labels.append("LOW SCORE")
        if item is upset and name == str(item.get("winner") or ""):
            labels.append("BIGGEST UPSET")
        return labels

    def matchup_badges(item):
        labels = []
        if item is close:
            labels.append("CLOSEST MATCHUP")
        if item is blow:
            labels.append("BIGGEST BLOWOUT")
        return labels

    def badge_html(labels, matchup=False):
        if not labels:
            return "&nbsp;"
        return " ".join(
            '<span style="display:inline-block;margin-left:4px;padding:2px 5px;background:#C58A2A;border:1px solid #FFFFFF;color:#FFFFFF;font-family:Arial,Helvetica,sans-serif;font-size:8px;line-height:11px;font-weight:bold;letter-spacing:.3px;white-space:nowrap;">{}</span>'.format(_e(label))
            for label in labels
        )

    def team_html(name):
        row = weekly_by_name.get(str(name), {})
        ap_record = all_play_text(name)
        ap_rank = all_play_rank(name)
        ap_detail = "{} · {}".format(ap_record, ap_rank) if ap_rank else ap_record
        return (
            '<div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:19px;font-weight:800;color:#112B3E;white-space:nowrap;">{}'
            '<span style="font-size:13px;font-weight:700;color:#112B3E;"> &middot; {}</span></div>'
            '<div style="margin-top:9px;font-family:Arial,Helvetica,sans-serif;font-size:11px;line-height:13px;font-weight:700;color:#667680;white-space:nowrap;text-transform:uppercase;">ALL PLAY&nbsp;&nbsp;{}</div>'
        ).format(_e(name), _e(wlt(row)), _e(ap_detail))

    for item in matchups:
        winner = str(item.get("winner") or "")
        loser = str(item.get("loser") or "")
        winner_badges = team_badges(item, winner)
        loser_badges = team_badges(item, loser)
        matchup_labels = matchup_badges(item)
        cards.append(
            '<table role="presentation" width="100%" height="178" cellspacing="0" cellpadding="0" border="0" style="width:100%;height:178px;border-collapse:collapse;border:1px solid #D9DFE3;background:#ffffff;">'
            '<tr><td height="68" valign="middle" style="height:68px;padding:8px 12px;background:#F7F8F8;border-bottom:1px solid #E1E5E8;">{}</td>'
            '<td width="94" height="68" align="center" valign="middle" bgcolor="#F4EBDD" style="height:68px;padding:6px;background:#F4EBDD;border-bottom:1px solid #E1E5E8;">'
            '<div style="font-family:Arial Black,Arial,Helvetica,sans-serif;font-size:22px;line-height:25px;font-weight:900;color:#8B5D17;">{}</div>'
            '<div style="height:17px;margin-top:3px;line-height:12px;overflow:hidden;">{}</div></td></tr>'
            '<tr><td height="68" valign="middle" style="height:68px;padding:8px 12px;border-bottom:1px solid #E1E5E8;">{}</td>'
            '<td width="94" height="68" align="center" valign="middle" style="height:68px;padding:6px;border-bottom:1px solid #E1E5E8;">'
            '<div style="font-family:Arial Black,Arial,Helvetica,sans-serif;font-size:20px;line-height:24px;font-weight:900;color:#112B3E;">{}</div>'
            '<div style="height:17px;margin-top:3px;line-height:12px;overflow:hidden;">{}</div></td></tr>'
            '<tr><td height="30" valign="middle" style="height:30px;padding:5px 8px 5px 12px;color:#667680;background:#FBFBFB;font-family:Arial,Helvetica,sans-serif;font-size:10px;letter-spacing:.8px;text-transform:uppercase;white-space:nowrap;">MARGIN: {} PTS</td>'
            '<td width="94" height="30" align="right" valign="middle" style="height:30px;padding:4px 6px;background:#FBFBFB;white-space:nowrap;">{}</td></tr></table>'.format(
                team_html(winner), _e(f(item["winner_score"])), badge_html(winner_badges),
                team_html(loser), _e(f(item["loser_score"])), badge_html(loser_badges),
                _e(f(item["margin"])), badge_html(matchup_labels, True),
            )
        )
    return _section("Matchup Results", _card_table(cards, 2))

def _weekly_highlights(ctx):
    """Weekly-only Beyond the Box Score, kept in this render slot for layout order."""
    glance = ctx.get("glance") or {}
    summary = ctx.get("lineup_summary") or {}
    weekly_rows = ctx.get("all_play_week") or []

    starter = glance.get("top_starter") or {}
    bench = glance.get("top_bench_player") or {}
    best = summary.get("best_efficiency") or {}
    worst = summary.get("worst_efficiency") or {}
    miss = summary.get("worst_decision") or {}
    deepest = summary.get("deepest_lineup") or {}
    most_bench = summary.get("most_bench_points") or summary.get("most_points_left") or {}

    def weekly_luck(row):
        result = str(row.get("actual_result") or "").upper()
        actual = 1.0 if result == "W" else (0.5 if result == "T" else 0.0)
        return actual - num(row.get("expected_weekly_wins"))

    lucky = max(weekly_rows, key=weekly_luck) if weekly_rows else {}
    unlucky = min(weekly_rows, key=weekly_luck) if weekly_rows else {}

    # Prefer Yahoo's pregame projection. If unavailable, compare with the
    # team's entering scoring average. Week 1 can legitimately have no
    # Overachiever card if projections are absent because there is no prior avg.
    over = {}
    over_detail = ""
    projected = [r for r in weekly_rows if num(r.get("projected_points")) > 0]
    if projected:
        over = max(projected, key=lambda r: num(r.get("points")) - num(r.get("projected_points")))
        over_detail = "{:+.2f}".format(num(over.get("points")) - num(over.get("projected_points")))
    else:
        current_week = int(num(ctx.get("week")))
        prior_by_team = {}
        for row in ctx.get("all_weekly_rows") or []:
            if int(num(row.get("week"))) < current_week:
                prior_by_team.setdefault(str(row.get("team_key") or ""), []).append(num(row.get("weekly_score")))
        candidates = []
        for row in weekly_rows:
            prior = prior_by_team.get(str(row.get("team_key") or "")) or []
            if prior:
                avg = sum(prior) / len(prior)
                candidates.append((num(row.get("points")) - avg, row))
        if candidates:
            delta, over = max(candidates, key=lambda x: x[0])
            over_detail = "{:+.2f}".format(delta)

    cards = [
        _highlight_card("Top Individual Performance", starter.get("player_name", "-"), "{} pts - {}".format(f(starter.get("points")), starter.get("team_name", "")).rstrip(" -"), 0) if starter else "",
        _highlight_card("Highest Scoring Bench Player", bench.get("player_name", "-"), "{} pts - {}".format(f(bench.get("points")), bench.get("team_name", "")).rstrip(" -"), 1) if bench else "",
        _highlight_card("Most Efficient Lineup", best.get("team_name", "-"), "{}%".format(f(best.get("lineup_efficiency"), 1)), 0) if best else "",
        _highlight_card("Least Efficient Lineup", worst.get("team_name", "-"), "{}%".format(f(worst.get("lineup_efficiency"), 1)), 1) if worst else "",
        _highlight_card("Luckiest", lucky.get("team_name", "-"), "{:+.2f} wins vs expected".format(weekly_luck(lucky)), 0) if lucky else "",
        _highlight_card("Unluckiest", unlucky.get("team_name", "-"), "{:+.2f} wins vs expected".format(weekly_luck(unlucky)), 1) if unlucky else "",
        _highlight_card("Overachiever", over.get("team_name", "-"), over_detail, 0) if over else "",
        _highlight_card("Biggest Lineup Miss", miss.get("team_name", "-"), "-{} pts".format(f(miss.get("decision_points_gained"))), 1) if miss else "",
        _highlight_card("Highest Floor", deepest.get("team_name", "-"), "{} pts".format(f(deepest.get("lowest_starter_points"))), 0) if deepest else "",
        _highlight_card("Most Points Left on Bench", most_bench.get("team_name", "-"), "{}".format(f(most_bench.get("bench_points"))), 1) if most_bench else "",
    ]
    cards = [card for card in cards if card]
    body = _card_table(cards, 2)
    if body:
        body += _note("Luck Rating = Actual Result - All-Play Win %, where Actual Result is 1 for a win, 0.5 for a tie, and 0 for a loss. Lineup Efficiency = Starting Lineup Score / Optimal Legal Lineup Score.")
    return _section("Beyond the Box Score", body)

def _pulse_stat(label, value, detail, width):
    return (
        '<td width="{}" valign="top" style="padding:0 5px;">'
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
        'style="width:100%;border-collapse:collapse;background:#FFFFFF;border:1px solid #D8DEE3;">'
        '<tr><td align="center" style="padding:13px 8px 12px 8px;font-family:Arial,Helvetica,sans-serif;text-align:center;">'
        '<div style="font-size:10px;line-height:13px;font-weight:bold;letter-spacing:.8px;color:#52606D;text-transform:uppercase;">{}</div>'
        '<div style="margin-top:5px;font-family:Arial Black,Arial,Helvetica,sans-serif;font-size:24px;line-height:28px;font-weight:900;color:#112B3E;">{}</div>'
        '<div style="margin-top:4px;font-size:10px;line-height:13px;color:#7A858C;">{}</div>'
        '</td></tr></table></td>'
    ).format(width, _e(label), _e(value), _e(detail))


def _league_pulse(ctx):
    pulse = ctx.get("league_pulse") or {}
    if not pulse:
        return ""

    week = int(num(ctx.get("week"), 0))
    team_count = int(num(pulse.get("team_count"), 0))

    if week == 1:
        point_stats = [
            ("Points This Week", f(pulse.get("week_points")), "All starting lineups"),
            ("Avg Team Score", f(pulse.get("avg_team_score")), "Across all {} teams".format(team_count or 12)),
        ]
        td_stats = [
            ("TDs This Week", f(pulse.get("week_touchdowns"), 0), "TDs scored by starters"),
        ]
    else:
        point_stats = [
            ("Points This Week", f(pulse.get("week_points")), "All starting lineups"),
            ("Points This Season", f(pulse.get("season_points")), "All starters through Week {}".format(week)),
            ("Points / Week", f(pulse.get("points_per_week")), "League average through Week {}".format(week)),
            ("Avg Team Score", f(pulse.get("avg_team_score")), "This week across {} teams".format(team_count or 12)),
        ]
        td_stats = [
            ("TDs This Week", f(pulse.get("week_touchdowns"), 0), "TDs scored by starters"),
            ("TDs This Season", f(pulse.get("season_touchdowns"), 0), "Starter TDs through Week {}".format(week)),
            ("TDs / Week", f(pulse.get("touchdowns_per_week"), 1), "League average through Week {}".format(week)),
        ]

    def band(title, stats):
        width = "{}%".format(int(100 / len(stats)))
        cells = "".join(_pulse_stat(label, value, detail, width) for label, value, detail in stats)
        return (
            '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="width:100%;border-collapse:collapse;">'
            '<tr><td style="padding:0 5px 7px 5px;font-family:Arial Black,Arial,Helvetica,sans-serif;font-size:11px;line-height:14px;font-weight:900;letter-spacing:1.2px;color:#C58A2A;text-transform:uppercase;">{}</td></tr>'
            '<tr><td><table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="width:100%;border-collapse:collapse;"><tr>{}</tr></table></td></tr>'
            '</table>'
        ).format(_e(title), cells)

    body = band("Points", point_stats)
    body += '<div style="height:14px;line-height:14px;">&nbsp;</div>'
    body += band("Touchdowns", td_stats)
    return _section("League Pulse", body)


def _display_record(row):
    return "{}-{}-{}".format(
        int(num(row.get("actual_wins"))),
        int(num(row.get("actual_losses"))),
        int(num(row.get("actual_ties"))),
    )


def _standings(ctx, final=False):
    rows = [[
        _e(r.get("standings_rank", "")),
        _e(r.get("team_name", "")),
        _e(_display_record(r)),
        _e(f(r.get("points_for"))),
        _e(movement(r.get("standings_movement"))),
        _e(r.get("current_streak", "")),
    ] for r in ctx.get("weekly_rows", [])]
    return _section(
        "Final Regular-Season Standings" if final else "Standings",
        _table(["Rank", "Team", "Record", "PF", "Move", "Streak"], rows,
               ["8%", "38%", "13%", "14%", "12%", "15%"],
               alignments=["center", "left", "center", "center", "center", "center"])
    )


def _power_rankings(ctx, final=False):
    weekly_by_key = {str(r.get("team_key") or ""): r for r in (ctx.get("weekly_rows") or [])}
    luck_by_key = {str(r.get("team_key") or ""): r for r in (ctx.get("luck") or [])}
    sos_by_key = {str(r.get("team_key") or ""): r for r in (ctx.get("sos") or [])}

    rows = []
    for r in ctx.get("power", []):
        key = str(r.get("team_key") or "")
        season = weekly_by_key.get(key, {})
        luck = luck_by_key.get(key, {})
        sos = sos_by_key.get(key, {})
        ap_w = int(num(season.get("all_play_wins")))
        ap_l = int(num(season.get("all_play_losses")))
        ap_t = int(num(season.get("all_play_ties")))
        ap_record = "{}-{}-{}".format(ap_w, ap_l, ap_t)
        rows.append([
            _e(r.get("power_rank", "")),
            '<span style="white-space:nowrap;">{}</span>'.format(_e(r.get("team_name", ""))),
            _e(f(r.get("power_score"))),
            _e(f(r.get("season_points"))),
            _e(ap_record),
            _e(pct(r.get("all_play_win_pct"))),
            _e("{:+.2f}".format(num(luck.get("luck_wins")))),
            _e(f(sos.get("avg_opponent_score"))),
            _e(_display_record(season)),
        ])
    body = _table(
        ["Rank", "Team", "Power", "PF", "AP Record", "AP %", "Luck", "Opp Avg", "Record"],
        rows,
        ["5%", "27%", "8%", "8%", "12%", "8%", "8%", "12%", "10%"],
        alignments=["center", "left", "center", "center", "center", "center", "center", "center", "center"],
    )
    if body:
        body += _note("All-Play, Luck and Opp Avg are season-to-date through this week. Power Ranking Formula: 30% season scoring - 25% all-play - 35% recent form - 10% record")
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
            '<div style="margin-top:10px;padding:10px 12px;background:#F7F8F8;'
            'border-left:3px solid #C6923D;font-family:Arial,Helvetica,sans-serif;'
            'color:#52606D;font-size:12px;line-height:18px;">{}</div>'
        ).format(_e(description))
    return body


def _challenge_update(ctx, results=False):
    data = ctx.get("challenge_data") or {}
    if not data:
        return ""
    standings = data.get("standings") or []
    left = (
        '<table role="presentation" width="100%" height="286" cellspacing="0" cellpadding="0" border="0" '
        'style="width:100%;height:286px;border-collapse:collapse;background:#F7F8F8;border:1px solid #DCE1E4;">'
        '<tr><td valign="middle" style="padding:18px 20px;font-family:Arial,Helvetica,sans-serif;">'
        '<table role="presentation" cellspacing="0" cellpadding="0" border="0" style="border-collapse:collapse;"><tr>'
        '<td width="54" valign="top" style="width:54px;padding-right:12px;"><div style="width:46px;height:46px;line-height:46px;text-align:center;background:#F4EBDD;border:1px solid #D7B77A;font-family:Arial Black,Arial,sans-serif;font-size:24px;font-weight:900;color:#A66D12;">&#9678;</div></td>'
        '<td valign="middle"><div style="font-size:12px;line-height:15px;color:#A66D12;font-weight:bold;letter-spacing:1.2px;text-transform:uppercase;">{} &#8226; ${} PRIZE</div>'
        '<div style="margin-top:5px;font-family:Arial Black,Arial,sans-serif;font-size:28px;line-height:31px;font-weight:900;color:#112B3E;">{}</div></td>'
        '</tr></table>'
        '<div style="margin-top:15px;color:#52606D;font-size:15px;line-height:22px;">{}</div>'
        '</td></tr></table>'
    ).format(_e(data.get("weeks", "")), _e(data.get("prize", 10)), _e(data.get("name", "-")), _e(data.get("description", "")))
    rows = []
    for row in standings[:12]:
        rank = row.get("rank", "")
        bg = "background:#F4EBDD;" if str(rank) == "1" else ""
        rows.append(
            '<tr><td width="28" style="padding:4px 5px;{}border-bottom:1px solid #E1E5E8;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#52606D;">{}</td>'
            '<td style="padding:4px 5px;{}border-bottom:1px solid #E1E5E8;font-family:Arial,Helvetica,sans-serif;font-size:12px;font-weight:bold;color:#112B3E;white-space:nowrap;overflow:hidden;">{}</td>'
            '<td width="58" align="right" style="padding:4px 5px;{}border-bottom:1px solid #E1E5E8;font-family:Arial,Helvetica,sans-serif;font-size:12px;font-weight:bold;color:#112B3E;">{}</td></tr>'.format(
                bg, _e(rank), bg, _e(row.get("team_name", "")), bg, _e(row.get("value", ""))
            )
        )
    right = (
        '<table role="presentation" width="100%" height="286" cellspacing="0" cellpadding="0" border="0" style="width:100%;height:286px;border-collapse:collapse;border:1px solid #DCE1E4;background:#FFFFFF;">'
        '<tr><td colspan="3" style="padding:8px 8px;background:#E7ECEF;border-bottom:2px solid #AEB8BF;font-family:Arial Black,Arial,sans-serif;font-size:12px;color:#112B3E;text-transform:uppercase;letter-spacing:.5px;">Challenge Standings</td></tr>{}</table>'
    ).format("".join(rows))
    body = '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="width:100%;border-collapse:collapse;table-layout:fixed;"><tr><td width="44%" valign="top" style="padding:5px;">{}</td><td width="56%" valign="top" style="padding:5px;">{}</td></tr></table>'.format(left, right)
    return _section("Challenge Results" if results else "Challenge Update", body)


def _challenge_standings(ctx):
    # Current challenge standings are rendered beside Challenge Update.
    return ""

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
            '<div style="margin-top:10px;padding:10px 12px;background:#F7F8F8;'
            'border-left:3px solid #C6923D;font-family:Arial,Helvetica,sans-serif;'
            'color:#52606D;font-size:12px;line-height:18px;">{}</div>'
        ).format(_e(nxt["description"]))
    return _section("Next Challenge", body)


def _upcoming_matchups(ctx, title="Next Week's Matchups"):
    data = ctx.get("upcoming_data") or {}
    matchups = data.get("matchups") or []
    cards = []
    for index, item in enumerate(matchups):
        a, b = item["team_a"], item["team_b"]
        featured = index == data.get("matchup_to_watch")
        badge = ""
        if featured:
            badge = '<div style="display:inline-block;margin:0 0 9px 0;padding:5px 9px;background:#C58A2A;color:#FFFFFF;font-family:Arial Black,Arial,sans-serif;font-size:11px;line-height:13px;font-weight:900;letter-spacing:.6px;text-transform:uppercase;">MATCHUP TO WATCH</div>'
        def team_line(team):
            rank = "#{}".format(team["power_rank"]) if team.get("power_rank") else "#-"
            projection = ""
            if team.get("projected_points") is not None and num(team.get("projected_points")) > 0:
                projection = '<div style="margin-top:3px;color:#A66D12;font-size:14px;line-height:17px;">Proj {}</div>'.format(_e(f(team.get("projected_points"))))
            return '<div style="font-family:Arial Black,Arial,Helvetica,sans-serif;font-size:15px;line-height:19px;font-weight:900;color:#112B3E;">{} {}</div><div style="margin-top:2px;color:#66727C;font-size:14px;line-height:17px;">{}</div>{}'.format(_e(rank), _e(team.get("team_name", "-")), _e(team.get("record", "")), projection)
        bg = "#FBF5E9" if featured else "#F7F8F8"
        border = "2px solid #C58A2A" if featured else "1px solid #D8DEE3"
        cards.append(
            '<table role="presentation" width="100%" height="174" cellspacing="0" cellpadding="0" border="0" style="width:100%;height:174px;border-collapse:collapse;background:{};border:{};">'
            '<tr><td height="174" valign="middle" style="height:174px;padding:15px 16px;font-family:Arial,Helvetica,sans-serif;color:#222A30;">{}{}'
            '<div style="padding:6px 0;color:#71808A;font-size:12px;line-height:14px;font-weight:bold;text-transform:uppercase;letter-spacing:1px;">vs</div>{}</td></tr></table>'.format(bg, border, badge, team_line(a), team_line(b))
        )
    subtitle = "Week {} - Rank shown is LeagueLab Power Ranking".format(data.get("week", ""))
    return _section(title, _card_table(cards, 2), subtitle)

def _from_commish(ctx):
    """Render commissioner notes as an opening editorial callout."""
    data = ctx.get("admin_data") or {}
    notes = data.get("notes") or data.get("items") or []
    if isinstance(notes, str):
        notes = [notes]
    notes = [str(item).strip() for item in notes if str(item).strip()]
    if not notes:
        return ""

    paragraphs = "".join(
        '<div style="margin:{};">{}</div>'.format(
            "0" if index == 0 else "10px 0 0 0",
            _e(item),
        )
        for index, item in enumerate(notes)
    )
    body = (
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
        'style="width:100%;border-collapse:collapse;background:#F7F3EB;border-left:4px solid #C58A2A;">'
        '<tr><td style="padding:16px 18px;font-family:Arial,Helvetica,sans-serif;color:#252A2E;'
        'font-size:15px;line-height:23px;">{}</td></tr></table>'.format(paragraphs)
    )
    return _section("From the Commissioner's Desk", body)


def _league_admin(ctx):
    """Render bottom-of-newsletter housekeeping only; commissioner notes live at the top."""
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
                    'style="border-collapse:separate;background:#F7F8F8;border:1px solid #D8DEE3;'
                    'border-radius:16px;"><tr><td style="padding:8px 12px;'
                    'font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:19px;'
                    'color:#222A30;white-space:nowrap;">{} &#8212; ${:.0f}</td></tr></table></td>'.format(
                        _e(x.get("team_name", "")),
                        num(x.get("balance_due", x.get("balance", 0))),
                    )
                )
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
            'style="width:100%;border-collapse:collapse;background:#F7F8F8;border:1px solid #D8DEE3;">'
            '<tr><td style="padding:12px 13px;font-family:Arial,Helvetica,sans-serif;font-size:13px;line-height:18px;">'
            '<div style="margin-bottom:5px;color:#C6923D;font-size:8px;font-weight:bold;'
            'text-transform:uppercase;">{}</div><strong>{}</strong>'
            '<div style="padding:4px 0;color:#66727C;font-size:10px;text-transform:uppercase;">vs</div>'
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
                '<tr><td colspan="3" style="padding:8px;background:#ffffff;color:#8B969E;'
                'font-family:Arial,Helvetica,sans-serif;font-size:11px;font-style:italic;">TBD</td></tr>'
            )
        winner = winner_key and str(team.get("team_key") or "") == str(winner_key)
        complete = bool(winner_key)
        bg = "#F5F1E8" if winner else "#ffffff"
        weight = "font-weight:bold;" if winner else ""
        deco = "text-decoration:line-through;color:#7A858D;" if complete and not winner else ""
        score = team.get("score")
        proj = team.get("projected_points")
        value = f(score) if score is not None else ("Proj {}".format(f(proj)) if proj is not None and num(proj) > 0 else "")
        return (
            '<tr><td width="34" style="padding:8px;background:{};font-family:Arial,Helvetica,sans-serif;'
            'font-size:10px;color:#66727C;{}">#{}</td>'
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
        'style="width:100%;border-collapse:collapse;border:1px solid #D8DEE3;background:#ffffff;">'
        '<tr><td colspan="3" align="center" style="padding:6px 8px;background:#222A30;color:#ffffff;'
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
        'style="width:100%;border-collapse:collapse;border:1px dashed #C9D0D5;">'
        '<tr><td align="center" style="padding:12px;font-family:Arial,Helvetica,sans-serif;'
        'font-size:11px;line-height:15px;color:#66727C;">Quarterfinal losers</td></tr>'
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
        '<div style="margin-bottom:8px;color:#142B3D;font-family:Arial,Helvetica,sans-serif;'
        'font-size:13px;line-height:16px;font-weight:bold;text-transform:uppercase;'
        'letter-spacing:.6px;">Championship Bracket</div>'
        + championship
        + '<div style="margin:22px 0 8px;color:#142B3D;font-family:Arial,Helvetica,sans-serif;'
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
        '<div style="margin-bottom:8px;color:#142B3D;font-family:Arial,Helvetica,sans-serif;'
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
        'style="width:100%;border-collapse:collapse;background:#F5F1E8;border:1px solid #D8C49C;">'
        '<tr><td align="center" style="padding:18px 20px;font-family:Arial,Helvetica,sans-serif;">'
        '<div style="font-size:52px;line-height:56px;margin-bottom:8px;">&#127942;</div>'
        '<div style="font-size:10px;text-transform:uppercase;letter-spacing:1px;'
        'color:#66727C;font-weight:bold;">League Champion</div>'
        '<div style="margin-top:5px;font-size:22px;font-weight:bold;color:#142B3D;">#{} {}</div>'
        '</td></tr></table>'
    ).format(_e(champion.get("seed", "-")), _e(champion.get("team_name", "-")))
    return _section("League Champion", body)


def _toilet_bowl_winner(ctx):
    champion = ((ctx.get("postseason_data") or {}).get("toilet_bowl") or {}).get("champion") or {}
    if not champion:
        return ""
    body = (
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
        'style="width:100%;border-collapse:collapse;background:#F5F1E8;border:1px solid #D8C49C;">'
        '<tr><td align="center" style="padding:18px 20px;font-family:Arial,Helvetica,sans-serif;">'
        '<div style="font-size:52px;line-height:56px;margin-bottom:8px;">&#128701;</div>'
        '<div style="font-size:10px;text-transform:uppercase;letter-spacing:1px;'
        'color:#66727C;font-weight:bold;">Toilet Bowl Champion</div>'
        '<div style="margin-top:5px;font-size:22px;font-weight:bold;color:#142B3D;">#{} {}</div>'
        '<div style="margin-top:5px;color:#66727C;font-size:12px;">${:.0f} payout</div>'
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
            ("#F7F8F8", "#C6923D"),
            ("#F7F8F8", "#142B3D"),
            ("#F7F8F8", "#6F7C85"),
        )
        background, border = palettes[index % 3]
        cards.append(
            '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
            'style="width:100%;border-collapse:collapse;background:{};border-left:3px solid {};">'
            '<tr><td valign="top" style="padding:14px 15px;font-family:Arial,Helvetica,sans-serif;">'
            '<div style="font-size:24px;line-height:28px;">{}</div>'
            '<div style="margin-top:7px;font-size:10px;line-height:13px;text-transform:uppercase;'
            'letter-spacing:.7px;color:#66727C;font-weight:bold;">{}</div>'
            '<div style="margin-top:6px;font-size:16px;line-height:20px;font-weight:bold;'
            'color:#142B3D;">{}</div>'
            '<div style="margin-top:5px;color:#66727C;font-size:12px;line-height:16px;">{}</div>'
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
        "from_commish": _from_commish,
        "matchup_results": _matchup_results,
        "weekly_highlights": _weekly_highlights,
        "league_pulse": _league_pulse,
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
        "league_pulse": analytics_result.get("league_pulse") or {},
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
        "week_1": "Opening Week",
        "regular_season": "Regular Season",
        "regular_season_final": "Regular Season Finale",
        "playoffs": "Playoffs",
        "championship": "Championship Week",
        "postseason_wrap": "Season Wrap-Up",
    }

    # Open with the commissioner message immediately below the newsletter header.
    # League Admin remains at the bottom for dues/housekeeping and does not repeat notes.
    content_parts = [_from_commish(ctx)]
    content_parts.extend(_render(name, ctx) for name in blocks_for(ntype))
    content = "".join(content_parts)

    # Keep the same 900px canvas that proved reliable in the preseason email.
    return (
        '<!doctype html><html><head>'
        '<meta http-equiv="Content-Type" content="text/html; charset=utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>LeagueLab Week {}</title></head>'
        '<body style="margin:0;padding:0;background:#F1F3F4;">'
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
        'bgcolor="#F1F3F4" style="width:100%;border-collapse:collapse;'
        'mso-table-lspace:0pt;mso-table-rspace:0pt;">'
        '<tr><td align="center" valign="top" style="padding:0;">'
        '<table role="presentation" width="900" cellspacing="0" cellpadding="0" border="0" '
        'align="center" style="width:900px;border-collapse:collapse;background:#FFFFFF;'
        'mso-table-lspace:0pt;mso-table-rspace:0pt;">'
        '<tr><td align="left" bgcolor="#112B3E" style="padding:0;background:#112B3E;font-family:Arial,Helvetica,sans-serif;color:#ffffff;text-align:left;">'
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="width:100%;border-collapse:collapse;"><tr>'
        '<td valign="middle" style="padding:27px 30px 28px 30px;">'
        '<div style="margin:0 0 6px;color:#D59A35;font-size:11px;line-height:14px;font-weight:bold;letter-spacing:2.5px;">LEAGUELAB</div>'
        '<div style="margin:0;font-family:Arial Black,Arial,Helvetica,sans-serif;font-size:32px;line-height:37px;font-weight:900;letter-spacing:-.6px;">{}</div>'
        '<div style="margin-top:7px;color:#E0B15E;font-family:Georgia,Times New Roman,serif;font-size:14px;line-height:19px;font-style:italic;font-weight:bold;">If you ain&#39;t first, you&#39;re last...</div>'
        '<div style="margin-top:9px;color:#D7DEE2;font-size:11px;line-height:17px;letter-spacing:1.2px;text-transform:uppercase;">{} &#8226; WEEK {} &#8226; {}</div></td>'
        '<td width="150" align="center" valign="middle" style="width:150px;padding:18px 24px;border-left:2px solid #C58A2A;">'
        '<div style="font-size:9px;line-height:12px;letter-spacing:2px;color:#D7DEE2;text-transform:uppercase;">WEEK</div>'
        '<div style="font-family:Arial Black,Arial,sans-serif;font-size:46px;line-height:48px;font-weight:900;color:#FFFFFF;">{}</div>'
        ''
        '</td></tr></table></td></tr>'
        '<tr><td align="left" style="padding:0;text-align:left;">{}</td></tr>'
        '<tr><td align="center" style="padding:20px 28px;font-family:Arial,Helvetica,sans-serif;'
        'text-align:center;color:#66727C;font-size:10px;letter-spacing:.5px;">XTREME FOOTBALL &#8226; Generated by LeagueLab</td></tr>'
        '</table></td></tr></table></body></html>'
    ).format(
        _e(week), _e(league_name), _e(season), _e(week), _e(labels[ntype]), _e(week), content
    )
