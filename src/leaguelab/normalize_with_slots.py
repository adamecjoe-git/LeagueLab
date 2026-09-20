"""Compatibility entry point; normalization lives in leaguelab.normalize."""

from leaguelab.normalize import *  # noqa: F401,F403
from leaguelab.normalize import main


if __name__ == "__main__":
    main()
