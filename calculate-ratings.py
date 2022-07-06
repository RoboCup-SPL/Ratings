#! /usr/bin/env python3

from dataclasses import dataclass
import math
import sqlite3
import sys


INITIAL_RATING = 1500
INITIAL_RD = 350
RD_TIME_FACTOR = 26.5  # also known as c - This value achieves a good prediction performance on previous games.
Q = math.log(10) / 400.0


@dataclass
class Team:
    name: str
    rating: float
    rd: float
    last_event: None


@dataclass
class Event:
    id: int
    name: str
    year: int
    month: int


@dataclass
class Game:
    home: int
    away: int
    goals_home: int
    goals_away: int
    p_goals_home: int
    p_goals_away: int


def g(rd):
    return 1.0 / math.sqrt(1.0 + (3.0 * Q * Q * rd * rd) / (math.pi * math.pi))


def expectation(own_rating, opponent_rating, rd):
    return 1.0 / (1.0 + math.exp(-g(rd) * Q * (own_rating - opponent_rating)))


def to_opponent_and_result(game, me):
    def points(my_g, my_p_g, opp_g, opp_p_g):
        if my_g > opp_g or (my_g == opp_g and my_p_g is not None and opp_p_g is not None and my_p_g > opp_p_g):
            return 1
        elif opp_g > my_g or (opp_g == my_g and my_p_g is not None and opp_p_g is not None and opp_p_g > my_p_g):
            return 0
        return 0.5
    if game.home == me:
        return game.away, points(game.goals_home, game.p_goals_home, game.goals_away, game.p_goals_away)
    elif game.away == me:
        return game.home, points(game.goals_away, game.p_goals_away, game.goals_home, game.p_goals_home)
    assert False


if __name__ == "__main__":
    connection = sqlite3.connect("file:spl_data.db?mode=ro", uri=True)
    cursor = connection.cursor()

    cursor.execute("SELECT ID, Name FROM Teams")
    teams = {_[0]: Team(_[1], INITIAL_RATING, INITIAL_RD, None) for _ in cursor.fetchall()}

    cursor.execute("SELECT ID, Name, Year, Month FROM Events ORDER BY Year, Month")
    events = [Event(*_) for _ in cursor.fetchall()]

    for event in events:
        cursor.execute("SELECT Home, Away, GoalsHome, GoalsAway, PGoalsHome, PGoalsAway FROM Games WHERE EventID = ? ORDER BY ID", (event.id,))
        games_this_event = [Game(*_) for _ in cursor.fetchall()]
        teams_this_event = set([_.home for _ in games_this_event] + [_.away for _ in games_this_event])  # could also be an SQL query, but would be quite unnecessary here.

        # 1. Calculate RD*
        for t in teams_this_event:
            if teams[t].last_event is None:
                continue
            time_since_last_event = (event.year - teams[t].last_event[0]) * 12 + (event.month - teams[t].last_event[1])
            teams[t].rd = min(math.sqrt(teams[t].rd * teams[t].rd + RD_TIME_FACTOR * RD_TIME_FACTOR * time_since_last_event), INITIAL_RD)

        print("")
        print(f"# Before {event.name} {event.year} (RD already updated)")
        for t in sorted(teams_this_event, key=lambda _: teams[_].rating, reverse=True):
            print(f"  {teams[t].name}: {teams[t].rating}, {teams[t].rd}")

        # 2. Calculate new ratings and final RDs.
        # They are written to a temporary variable because all calculations must still be made with the old data.
        new_ratings = {}
        new_rds = {}
        for t in teams_this_event:
            games_this_team = [_ for _ in games_this_event if _.home == t or _.away == t]
            games_this_team = [to_opponent_and_result(_, t) for _ in games_this_team]
            # print(f"{teams[t].name}: {games_this_team}")
            d_squared_inv = Q * Q * sum(g(teams[opponent].rd) * g(teams[opponent].rd) * expectation(teams[t].rating, teams[opponent].rating, teams[opponent].rd) * (1.0 - expectation(teams[t].rating, teams[opponent].rating, teams[opponent].rd)) for opponent, _ in games_this_team)
            new_rd_squared_inv = 1 / (teams[t].rd * teams[t].rd) + d_squared_inv
            new_ratings[t] = teams[t].rating + Q / new_rd_squared_inv * sum(g(teams[opponent].rd) * (result - expectation(teams[t].rating, teams[opponent].rating, teams[opponent].rd)) for opponent, result in games_this_team)
            new_rds[t] = math.sqrt(1 / new_rd_squared_inv)


        for t in teams_this_event:
            teams[t].rating = new_ratings[t]
            teams[t].rd = new_rds[t]
            teams[t].last_event = (event.year, event.month)

        print("")
        print(f"# After {event.name} {event.year}")
        for t in sorted(teams_this_event, key=lambda _: teams[_].rating, reverse=True):
            print(f"  {teams[t].name}: {teams[t].rating}, {teams[t].rd}")


    print("")
    print(f"# Final Ratings")
    for i, t in enumerate(sorted(teams.values(), key=lambda _: _.rating, reverse=True)):
        # If RD was printed here, it should be noted that it is immediately after the last event, i.e. RD does not include the increased uncertainty.
        print(f"{i+1:02}:  {t.name} - {t.rating}")
