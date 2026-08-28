"""
Single source of truth for the Phase 4 county-council routing rows that were
present in the authoritative source (Excel Criteria/County_Councils_Criteria.md)
but missing from the hand-typed COUNTY_DISTRICTS dict in migration 0010:
Derbyshire, Dorset, North Yorkshire, Staffordshire (32 districts).

Each routing row is PINNED to its exact CouncilRule via the council_rule FK
rather than relying on fuzzy name resolution, because:
  - 2 districts mis-resolve by name to the WRONG authority
    (Newcastle Borough -> Newcastle-upon-Tyne; Lichfield District -> a parish),
  - reorganised unitaries (North Yorkshire, Dorset) must override legacy
    per-district statuses with the new single-authority decision,
  - some target rules have composite names the resolver can't reach
    (e.g. "Stafford Borough Council + Cannock Council (work together)").

`_phase4_county_council` prefers routing.council_rule when set, so these pins
are honoured exactly.

Both migration 0054 and the `seed_all_councils` management command call
`seed_county_routing()` so the data lives in ONE place. CouncilRule rows are
seeded by `seed_all_councils` (not by migrations), so:
  - when councils are already present (live DB / after seeding) pinning is
    STRICT: a missing, ambiguous, or status-drifted rule raises;
  - when the CouncilRule table is empty (fresh/test DB built from migrations
    only) the routing rows are still created, with a null FK, and pinning is
    deferred to the next `seed_all_councils` run.

Decisions encoded (confirmed with product owner 2026-06-21):
  - North Yorkshire & Dorset: NEW unitary decision for all districts
    (North Yorkshire Council = DO_NOT_VOTE; mainland Dorset = Dorset Council
    WILL_CONSIDER; Christchurch/Bournemouth/Poole = BCP REJECT).
  - Lichfield District -> Lichfield City Council (ACCEPT).
  - Amber Valley -> trust Councils.md (DO_NOT_VOTE) over the county file's
    inline "Reject" note (decisions live in Councils.md / CouncilRule).
"""

# (county, district_name, [tokens identifying the CouncilRule], expected_status)
# expected_status is asserted post-lookup as a second guard against mis-pinning.
ROUTING = [
    # --- Derbyshire (8) — resolve to their own district rules ---
    ("Derbyshire", "Derbyshire Dales",       ["Derbyshire Dales"],        "ACCEPT"),
    ("Derbyshire", "South Derbyshire",       ["South Derbyshire"],        "REJECT"),
    ("Derbyshire", "Erewash",                ["Erewash"],                 "DO_NOT_VOTE"),
    ("Derbyshire", "Amber Valley",           ["Amber Valley"],            "DO_NOT_VOTE"),
    ("Derbyshire", "North East Derbyshire",  ["North East Derbyshire"],   "ACCEPT"),
    ("Derbyshire", "Chesterfield",           ["Chesterfield"],            "DO_NOT_VOTE"),
    ("Derbyshire", "Bolsover District",      ["Bolsover"],                "DO_NOT_VOTE"),
    ("Derbyshire", "Derby",                  ["Derby City"],              "ACCEPT"),

    # --- Dorset (8) — NEW unitary: mainland -> Dorset Council; BCP for the 3 ---
    ("Dorset", "Weymouth and Portland", ["Dorset", "Direct"], "WILL_CONSIDER"),
    ("Dorset", "West Dorset",           ["Dorset", "Direct"], "WILL_CONSIDER"),
    ("Dorset", "North Dorset",          ["Dorset", "Direct"], "WILL_CONSIDER"),
    ("Dorset", "Purbeck District",      ["Dorset", "Direct"], "WILL_CONSIDER"),
    ("Dorset", "East Dorset",           ["Dorset", "Direct"], "WILL_CONSIDER"),
    ("Dorset", "Christchurch",          ["BCP"],              "REJECT"),
    ("Dorset", "Bournemouth",           ["BCP"],              "REJECT"),
    ("Dorset", "Poole",                 ["BCP"],              "REJECT"),

    # --- North Yorkshire (7) — NEW unitary: all -> North Yorkshire Council ---
    ("North Yorkshire", "Scarborough",   ["North Yorkshire County Council"], "DO_NOT_VOTE"),
    ("North Yorkshire", "Ryedale",       ["North Yorkshire County Council"], "DO_NOT_VOTE"),
    ("North Yorkshire", "Hambleton",     ["North Yorkshire County Council"], "DO_NOT_VOTE"),
    ("North Yorkshire", "Selby",         ["North Yorkshire County Council"], "DO_NOT_VOTE"),
    ("North Yorkshire", "Harrogate",     ["North Yorkshire County Council"], "DO_NOT_VOTE"),
    ("North Yorkshire", "Richmondshire", ["North Yorkshire County Council"], "DO_NOT_VOTE"),
    ("North Yorkshire", "Craven",        ["North Yorkshire County Council"], "DO_NOT_VOTE"),

    # --- Staffordshire (9) ---
    ("Staffordshire", "Cannock Chase District",   ["Cannock Chase"],            "REJECT"),
    ("Staffordshire", "East Staffordshire",       ["East Staffordshire"],       "REJECT"),
    ("Staffordshire", "Lichfield District",       ["Lichfield City"],           "ACCEPT"),
    ("Staffordshire", "Newcastle Borough",        ["Newcastle-under-Lyme"],     "DO_NOT_VOTE"),
    ("Staffordshire", "South Staffordshire",      ["South Staffordshire"],      "WILL_CONSIDER"),
    ("Staffordshire", "Stafford Borough Council", ["Stafford Borough Council +"], "REJECT"),
    ("Staffordshire", "Staffordshire Moorlands",  ["Staffordshire Moorlands"],  "DO_NOT_VOTE"),
    ("Staffordshire", "Stoke On Trent",           ["Stoke-on-Trent City"],      "WILL_CONSIDER"),
    ("Staffordshire", "Tamworth",                 ["Tamworth"],                 "REJECT"),
]

COUNTIES = ["Derbyshire", "Dorset", "North Yorkshire", "Staffordshire"]


# Existing routing rows (already in CountyCouncilRouting from migration 0010)
# whose abbreviated district_name does not resolve to a CouncilRule by name,
# but for which a single unambiguous rule DOES exist. We pin the FK so the
# decision is reached exactly. district_name MUST match the existing DB row
# verbatim (so we update that row, never create a duplicate).
#
# Tokens were verified to match exactly ONE CouncilRule each, with the status
# shown; _find_rule re-checks both at seed time and refuses to pin otherwise.
#
# Two are local-government reorganisations resolved with the same NEW-unitary
# principle confirmed for North Yorkshire/Dorset (product owner, 2026-06-21):
#   East Northamptonshire & South Northamptonshire -> the unitaries that
#   absorbed them (North / West Northamptonshire), both REJECT. East
#   Northamptonshire's own county-file note independently says "Reject".
#
# (county, EXACT existing district_name, [tokens], expected_status)
ALIAS_PINS = [
    ("Cambridgeshire",          "Fenland DC",                ["Fenland District Council"],   "REJECT"),
    ("Lancashire",              "Blackpool UA",              ["Blackpool Council"],          "REJECT"),
    ("Lincolnshire",            "Boston BC",                 ["Boston Borough Council"],     "DO_NOT_VOTE"),
    ("Lincolnshire",            "West Lindsey DC",           ["West + East Lindsey"],        "REJECT"),
    ("Norfolk",                 "Breckland DC",              ["East Suffolk Council (COVERS"], "REJECT"),
    ("Northamptonshire",        "Wellingborough BC",         ["North Northamptonshire"],     "REJECT"),
    ("Northamptonshire",        "East Northamptonshire DC",  ["North Northamptonshire"],     "REJECT"),
    ("Northamptonshire",        "South Northamptonshire DC", ["West Northamptonshire"],      "REJECT"),
    ("Nottinghamshire",         "Ashfield DC",               ["Ashfield Borough Council"],   "DO_NOT_VOTE"),
    ("Surrey",                  "Spelthorne BC",             ["Spelthorne"],                 "WILL_CONSIDER"),
    ("West Sussex",             "Adur DC",                   ["Adur"],                       "DO_NOT_VOTE"),
    ("Yorkshire (East Riding)", "Kingston upon Hull CC",     ["Hull City Council"],          "DO_NOT_VOTE"),
]

# Districts with NO matching CouncilRule anywhere — deliberately NOT pinned;
# they remain "manual review required" rather than guessing a decision.
# (South Bucks, Broxbourne, Sevenoaks, Rutland, Basford, Oxford City — most are
# post-reorganisation or not a billing authority; Basford is a Nottingham area,
# likely a data artefact in the original COUNTY_DISTRICTS dict.)
UNPINNED_NO_RULE = [
    ("Buckinghamshire", "South Bucks DC"),
    ("Hertfordshire",   "Broxbourne BC"),
    ("Kent",            "Sevenoaks DC"),
    ("Leicestershire",  "Rutland Council"),
    ("Nottinghamshire", "Basford DC"),
    ("Oxfordshire",     "Oxford CC"),
]


def _find_rule(CouncilRule, tokens, expected_status, district, strict):
    """Return the unique CouncilRule for `tokens`, or None when councils are not
    yet seeded (strict=False). Raises on any ambiguity, status drift, or — when
    strict — a missing rule, so a wrong pin can never be seeded silently."""
    qs = CouncilRule.objects.all()
    for t in tokens:
        qs = qs.filter(council_name__icontains=t)
    rules = list(qs)
    if len(rules) == 0:
        if not strict:
            return None
        raise RuntimeError(
            f"Routing pin for '{district}': tokens {tokens} matched no "
            "CouncilRule. Run seed_all_councils first, or fix the tokens."
        )
    if len(rules) > 1:
        raise RuntimeError(
            f"Routing pin for '{district}': tokens {tokens} matched "
            f"{len(rules)} rules {[r.council_name for r in rules]!r} — "
            "expected exactly 1. Refusing to seed an ambiguous pin."
        )
    rule = rules[0]
    if rule.status != expected_status:
        raise RuntimeError(
            f"Routing pin for '{district}': matched '{rule.council_name}' has "
            f"status {rule.status!r}, expected {expected_status!r} "
            "(ground-truth drift). Refusing to seed."
        )
    return rule


def seed_county_routing(CouncilRule, CountyCouncilRouting, log=None, strict=False):
    """Create/refresh the 4 counties' routing rows and pin their council_rule FK.

    Idempotent. Accepts model classes so it works with both the historical
    models inside a migration and the live models inside the management command.

    strict=False (migration default): a district whose CouncilRule isn't present
    yet (councils are seeded by seed_all_councils, not by migrations) gets a
    routing row with a null FK; the next seed_all_councils run pins it.
    strict=True (management command): every district MUST pin — councils were
    just seeded, so a 0-match is a real error and raises.

    An ambiguous match (>1) or a status drift ALWAYS raises, regardless of
    `strict`, since those indicate a genuine ground-truth problem.
    """
    log = log or (lambda _m: None)
    created = pinned = 0
    for county, district, tokens, expected in ROUTING:
        rule = _find_rule(CouncilRule, tokens, expected, district, strict=strict)
        obj, was_created = CountyCouncilRouting.objects.get_or_create(
            county_name=county, district_name=district,
            defaults={"council_rule": rule},
        )
        created += int(was_created)
        if rule is not None and obj.council_rule_id != rule.id:
            obj.council_rule = rule
            obj.save(update_fields=["council_rule"])
        if rule is not None:
            pinned += 1
    log(f"County routing: {created} row(s) created, {pinned}/{len(ROUTING)} pinned"
        + ("" if pinned == len(ROUTING) else " (unpinned rows await a seed_all_councils run)") + ".")
    return created, pinned


def apply_alias_pins(CouncilRule, CountyCouncilRouting, log=None, strict=False):
    """Pin the council_rule FK on EXISTING routing rows whose abbreviated
    district_name doesn't resolve by name but has one unambiguous CouncilRule.

    Idempotent. Only updates rows that already exist (never creates), so a
    typo'd district_name is surfaced (logged) rather than silently duplicated.
    Ambiguous/status-drifted matches always raise; a 0-match raises only when
    strict (councils seeded), matching seed_county_routing's contract.
    """
    log = log or (lambda _m: None)
    pinned = missing_row = 0
    for county, district, tokens, expected in ALIAS_PINS:
        rule = _find_rule(CouncilRule, tokens, expected, district, strict=strict)
        if rule is None:
            continue  # councils not seeded yet — deferred to next run
        try:
            obj = CountyCouncilRouting.objects.get(county_name=county, district_name=district)
        except CountyCouncilRouting.DoesNotExist:
            missing_row += 1
            log(f"  alias pin: routing row '{county} / {district}' not found — skipped.")
            continue
        if obj.council_rule_id != rule.id:
            obj.council_rule = rule
            obj.save(update_fields=["council_rule"])
        pinned += 1
    log(f"Alias pins: {pinned}/{len(ALIAS_PINS)} existing districts pinned"
        + (f"; {missing_row} routing row(s) missing" if missing_row else "") + ".")
    return pinned, missing_row
