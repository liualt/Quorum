#!/usr/bin/env python3
"""Create an interview and print the two links a rehearsal needs.

The reviewer token is shown once, when the interview is created, and is never
readable again — so a demo that wants both sides open in two browsers has to
capture it at that moment. That is all this does.

    python3 scripts/seed_demo.py --name "Ada" --origin http://localhost:3000

The candidate link only works in the browser that holds the candidate cookie,
and this script holds it instead. Open the candidate link in a fresh browser
and it will refuse: create the interview from the consent page when a real
candidate is going to sit down. `QUORUM_BASE_URL` and `QUORUM_WEB_ORIGIN` set
the defaults.
"""

import argparse
import sys

from quorum_api import ApiError, Client, default_base_url, default_web_origin


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", default=default_base_url(), help="backend base URL")
    parser.add_argument("--origin", default=default_web_origin(), help="web app origin")
    parser.add_argument("--name", default="Demo candidate", help="display name for the interview")
    args = parser.parse_args(argv)

    client = Client(args.base, args.origin)
    try:
        created = client.post(
            "/api/interviews", {"display_name": args.name, "consent": True}
        )
    except ApiError as error:
        print(f"could not create the interview: {error}")
        return 1

    origin = args.origin.rstrip("/")
    print(f"interview      {created['id']}")
    print(f"candidate      {origin}{created['candidate_path']}")
    print(f"reviewer       {origin}{created['reviewer_path']}")
    print("\nThe reviewer link is shown once. The candidate link needs the cookie the")
    print("consent page sets, so start a real session from that page instead.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
