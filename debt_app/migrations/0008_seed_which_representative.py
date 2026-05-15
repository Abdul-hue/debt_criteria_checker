"""Seed Which Representative data.

Source: Which Representative sheet (288 rows), column mapping:
  Col 0 = TIX creditor names (rows 2–47)
  Col 2 = WATCH/WPM representative names (rows 2–287) with trading names as sub-rows
  Col 4 = EVOLVE creditor names (rows 3–7): Mint, NatWest Bank, The Royal Bank of Scotland Plc, TSB Bank, Ulster Bank

Structure:
  - Parent representative rows → CreditorCriteria with representative field and is_active=True
  - Trading name sub-rows → stored in trading_names JSONField on the parent row
  - Idempotent: filter(__iexact).first() to avoid duplicates
  - Reversible: clears only representative and trading_names, does not delete rows
"""

from django.db import migrations


TIX_CREDITORS = [
    "118 Money",
    "Alliance & Leicester",
    "Argos Mastercard",
    "Barclays Bank",
    "British Gas",
    "Blue Motor Finance",
    "Capital One",
    "Carval",
    "Creation Consumer Finance",
    "Debitas",
    "First Direct",
    "Freemans Catalogue",
    "Fresh Start",
    "Granite (Vanquis)",
    "Grattan",
    "HFC Bank",
    "Home Retail Group",
    "HSBC",
    "John Lewis Partnership",
    "Hitachi",
    "Lendable",
    "Laser UK",
    "Lombard",
    "Lowell Financial",
    "Marks & Spencer",
    "Opus",
    "Paypal Europe Ltd",
    "Sainsburys Bank",
    "Santander",
    "Santander Cards",
    "SAV Credit",
    "Shop Direct Group",
    "SSE",
    "Style Financial Services",
    "Sygma Bank Limited",
    "TTI Finance",
    "UKAR",
    "Vanquis Bank",
    "Welcome Financial Services Ltd",
    "Wonga",
    "Kaleidoscope",
    "Argos Card Services",
    "Moneybarn",
    "Santander Consumer Finance",
    "Look Again",
    "Creation Financial Services",
    "Southern Electric",
]

EVOLVE_CREDITORS = [
    "Mint",
    "NatWest Bank",
    "The Royal Bank of Scotland Plc",
    "TSB Bank",
    "Ulster Bank",
]

# WATCH/WPM representatives with their trading names
WATCH_REPRESENTATIVES = {
    "AA (Bank of Ireland) - IVA": [],
    "AA (Bank of Ireland) - TD": [],
    "Akinika / Kent Reliance (previously One Savings Bank) - IVA": [],
    "Akinika / Kent Reliance (previously One Savings Bank) - TD": [],
    "Apex Credit Management (now Cabot) - IVA": [],
    "Apex Credit Management (now Cabot) - TD": [],
    "Arrow Global Massey Ltd- IVA or BKY": [],
    "Arrow Global Massey Ltd- TD or DAS or SEQ": [],
    "Barclaycard (including cards below) - IVA": [
        "Argos Mastercard - IVA",
        "Barclaycard Motor Loans - IVA",
        "BHS Mastercard - IVA",
        "Goldfish - IVA",
        "Hilton Honours Visa - IVA",
        "Intercontinental Hotel Group Visa - IVA",
        "Littlewoods - IVA",
        "Morgan Stanley - IVA",
        "Orange - CREDIT CARD ONLY - IVA",
        "Priority Club Rewards Visa - IVA",
        "Sky Card - IVA",
        "Thomas Cook - IVA",
    ],
    "Barclaycard (including cards below) - TD": [
        "Argos Mastercard - TD",
        "Barclaycard Motor Loans - TD",
        "BHS Mastercard - TD",
        "Goldfish - TD",
        "Hilton Honours Visa - TD",
        "Intercontinental Hotel Group Visa - TD",
        "Littlewoods - TD",
        "Morgan Stanley - TD",
        "Orange - CREDIT CARD ONLY - TD",
        "Priority Club Rewards Visa - TD",
        "Sky Card - TD",
        "Thomas Cook - TD",
        "Barclaycard Amazon - IVA",
        "Barclaycard Amazon - TD",
        "Barclays Partner Finance (also known as Clydesdale Financial Services) - IVA",
        "Barclays Partner Finance (also known as Clydesdale Financial Services) - TD",
    ],
    "Cabot Financial (including DLC) - IVA": [],
    "Cabot Financial (including DLC) - TD": [],
    "The Co-operative Bank - IVA": [],
    "The Co-operative Bank - TD": [],
    "CYBG (Clydesdale Bank) - previously National Australia Group - IVA": [],
    "CYBG (Clydesdale Bank) - previously National Australia Group - TD": [],
    "CYBG (Yorkshire Bank) - previously National Australia Group - IVA": [],
    "CYBG (Yorkshire Bank) - previously National Australia Group - TD": [],
    "Grove / TTI SPC CarVal (including previous Egg Loans /Britannica Recovery) - IVA": [],
    "Grove / TTI SPC CarVal (including previous Egg Loans /Britannica Recovery) - TD": [],
    "IDEM / Paragon / Moorgate- IVA": [],
    "IDEM / Paragon / Moorgate- TD": [],
    "Ikano Bank AB - IVA or TD or BKY or DAS or SEQ or DRO": [
        "incl. New Look Card",
        "DFS Loan",
        "ScS Loan",
        "IKEA IFC",
        "IKEA Home Card",
        "IKEA Limited",
        "Ikano D2C Loan",
        "Oasis Card",
        "Warehouse Card",
        "Karen Millen Card",
        "Principles Card (loans taken out from 2006 onwards)",
        "Vision Express",
    ],
    "Intrum UK Ltd (previously 1st Credit) - IVA or BKY": [],
    "Intrum UK Ltd (previously 1st Credit) - TD or DAS or SEQ": [],
    "Jaja Finance Ltd": [],
    "Jefferson Capital International Acquisition (JCIA, or their UK operation Creditlink Account Recovery Services CARS)": [],
    "Kent Reliance / Akinika (previously One Savings Bank) - IVA": [],
    "Kent Reliance / Akinika (previously One Savings Bank) - TD": [],
    "La Redoute - IVA or TD or BKY or DAS or SEQ or DRO": [
        "incl. La Redoute",
        "LR UK (Retail) Limited",
        "Redcats UK",
        "Droyds",
        "Droyds Debt & Collection Services",
        "LR UK",
    ],
    "Lantern Debt Recovery Limited - IVA or BKY": [],
    "Lantern Debt Recovery Limited - TD or DAS or SEQ": [],
    "LC Asset - IVA & BKY": [],
    "LC Asset - TD": [],
    "Link Financial - IVA": [
        "incl. Link Financial Outsourcing",
        "Asset Link Capital",
        "Antelope Loans Funding Ltd",
        "IDR Finance UK Ltd",
        "Fortis Lease UK",
        "Bamboo Ltd",
    ],
    "Link Financial - TD": [
        "incl. Link Financial Outsourcing",
        "Asset Link Capital",
        "Antelope Loans Funding Ltd",
        "IDR Finance UK Ltd",
        "Fortis Lease UK",
        "Bamboo Ltd",
    ],
    "Lloyds Banking Group (Including the Companies/Brands below) - IVA": [
        "Lloyds - Create (Wealth Management) Card - IVA",
        "Lloyds - Lloyds (Mortgage Shortfall) - IVA",
        "Lloyds - LTSB Airmiles Duo Card - IVA",
        "Lloyds - LTSB American Express Private Banking Card - IVA",
        "Lloyds - LTSB Business Card - IVA",
        "HBOS - AA (HBOS) - IVA",
        "HBOS - Aqua (HBOS) - IVA",
        "HBOS - Bank of Scotland - IVA",
        "HBOS - Birmingham Midshires Mortgage Shortfall - IVA",
        "HBOS - Blair Oliver & Scott - IVA",
        "HBOS - Brit/Scot Gas Loans - IVA",
        "HBOS - Britannia Loans (HBOS) - IVA",
        "HBOS - Business Banking - IVA",
        "HBOS - Capital Bank - IVA",
        "HBOS - Cheltenham & Gloucester (Mortgage Shortfall) - IVA",
        "HBOS - GE Capital Loans - IVA",
        "HBOS - Halifax - IVA",
        "HBOS - Halifax (Mortgage Shortfall) - IVA",
        "HBOS - HBOS - IVA",
        "HBOS - HSPF - IVA",
        "HBOS - Intelligent Finance - IVA",
        "HBOS - Marbles (HBOS) - IVA",
        "HBOS - Renault Loans - IVA",
        "HBOS - Retail Recoveries - IVA",
        "HBOS - St James PB (HBOS) - IVA",
        "HBOS - The Mortgage Business (Mortgage Shortfall) - IVA",
        "Blackhorse - Blackhorse Finance - IVA",
        "Blackhorse - Honda Motorcycle Finance - IVA",
        "Blackhorse - International Motors (IM) Finance - IVA",
        "Blackhorse - Lloyds TSB CarSelect - IVA",
        "Blackhorse - Porsche - IVA",
        "Blackhorse - Proton Finance Ltd - IVA",
        "Blackhorse - Shogun Finance Ltd - IVA",
        "Blackhorse - Subaru Finance - IVA",
        "Blackhorse - Suzuki Financial Services Ltd - IVA",
        "Blackhorse - United Dominions Trust Ltd - IVA",
        "MBNA - IVA",
    ],
    "Lloyds Banking Group (Including the Companies/Brands below) - TD": [
        "Lloyds - Create (Wealth Management) Card - TD",
        "Lloyds - Lloyds (Mortgage Shortfall) - TD",
        "Lloyds - LTSB Airmiles Duo Card - TD",
        "Lloyds - LTSB American Express Private Banking Card - TD",
        "Lloyds - LTSB Business Card - TD",
        "HBOS - AA (HBOS) - TD",
        "HBOS - Aqua (HBOS) - TD",
        "HBOS - Bank of Scotland - TD",
        "HBOS - Birmingham Midshires Mortgage Shortfall - TD",
        "HBOS - Blair Oliver & Scott - TD",
        "HBOS - Brit/Scot Gas Loans - TD",
        "HBOS - Britannia Loans (HBOS) - TD",
        "HBOS - Business Banking - TD",
        "HBOS - Capital Bank - TD",
        "HBOS - Cheltenham & Gloucester (Mortgage Shortfall) - TD",
        "HBOS - GE Capital Loans - TD",
        "HBOS - Halifax - TD",
        "HBOS - Halifax (Mortgage Shortfall) - TD",
        "HBOS - HBOS - TD",
        "HBOS - HSPF - TD",
        "HBOS - Intelligent Finance - TD",
        "HBOS - Marbles (HBOS) - TD",
        "HBOS - Renault Loans - TD",
        "HBOS - Retail Recoveries - TD",
        "HBOS - St James PB (HBOS) - TD",
        "HBOS - The Mortgage Business (Mortgage Shortfall) - TD",
        "Blackhorse - Blackhorse Finance - TD",
        "Blackhorse - Honda Motorcycle Finance - TD",
        "Blackhorse - International Motors (IM) Finance - TD",
        "Blackhorse - Lloyds TSB CarSelect - TD",
        "Blackhorse - Porsche - TD",
        "Blackhorse - Proton Finance Ltd - TD",
        "Blackhorse - Shogun Finance Ltd - TD",
        "Blackhorse - Subaru Finance - TD",
        "Blackhorse - Suzuki Financial Services Ltd - TD",
        "Blackhorse - United Dominions Trust Ltd - TD",
        "MBNA - Bankruptcy and TD",
    ],
    "Lloyds Banking Group (Including the Companies/Brands above) - BKY/SEQ": [],
    "Marlin Financial - IVA": [],
    "Marlin Financial - TD": [],
    "Marlin ME IV (prev NRAM 6319) - IVA": [],
    "Marlin ME IV (prev NRAM 6319) - TD": [],
    "Monzo Bank": [],
    "Moorgate Loan Servicing (now IDEM) - IVA": [],
    "Moorgate Loan Servicing (now IDEM) - TD": [],
    "Nationwide Building Society - IVA": [],
    "Nationwide Building Society - TD": [],
    "New Day / PRA - IVA or BKY": [
        "Amazon - IVA, AO - IVA, Aqua - IVA, Arcadia - IVA, Argos - IVA, BIP,",
        "Burton Menswear - IVA, Debenhams - IVA, Dorothy Perkins - IVA, Evans - IVA,",
        "Fluid - IVA, Harvey Nichols - IVA, House of Frazer - IVA, John Lewis - IVA,",
        "Laura Ashley - IVA, Marbles - IVA, Miss Selfridge - IVA, NewPay - IVA,",
        "Opus - IVA, Outfit - IVA, Pulse - IVA, TUI/Thompson - IVA, Topman - IVA,",
        "Topshop - IVA, Wallis - IVA, 1:Many",
    ],
    "New Day / PRA - TD or SEQ": [
        "Amazon - TD, AO - TD, Aqua - TD, Arcadia - TD, Argos - TD, BIP,",
        "Burton Menswear - TD, Debenhams - TD, Dorothy Perkins - TD, Evans - TD,",
        "Fluid - TD, Harvey Nichols - TD, House of Frazer - TD, John Lewis - TD,",
        "Laura Ashley - TD, Marbles - TD, Miss Selfridge - TD, NewPay - TD,",
        "Opus - TD, Outfit - TD, Pulse - TD, TUI/Thompson - TD, Topman - TD,",
        "Topshop - TD, Wallis - TD, 1:Many - TD",
    ],
    "One Savings Bank (now known as Akinika / Kent Reliance) - IVA": [],
    "One Savings Bank (now known as Akinika / Kent Reliance) - TD": [],
    "Paragon / IDEM / Moorgate- IVA": [],
    "Paragon / IDEM / Moorgate- TD": [],
    "PCO Holdco Sarl - IVA": [],
    "PCO Holdco Sarl - TD": [],
    "Post Office incl Post Office Fin Svs (Bank of Ireland) - IVA": [],
    "Post Office incl Post Office Fin Svs (Bank of Ireland) - TD": [],
    "PRA (Portfolio Recovery Associates) - IVA": [],
    "PRA (Portfolio Recovery Associates) - TD": [],
    "Target / Elderbridge (previously First Plus UKSL and Swancastle) - IVA": [],
    "Target / Elderbridge (previously First Plus UKSL and Swancastle) - TD": [],
    "Thames Water": [],
    "The Very Group - IVA or TD": [
        "Shop Direct Financial Services, Littlewoods (SDG), Very (SDG), Very,",
        "Littlewoods, Empire (SDG), Marshall Ward, Kays, Great Universal, K&Co,",
        "Additions, Nationwide Recovery (SDG), Choice, Littlewoods Debt Collections,",
        "Shop Direct Finance Company, Abound",
    ],
    "TTI SPC CarVal / Grove (including previous Egg Loans /Britannica Recovery) - IVA": [],
    "TTI SPC CarVal / Grove (including previous Egg Loans /Britannica Recovery) - TD": [],
    "Zopa - IVA or BKY": [],
    "Zopa - TD or SEQ": [],
    "CapQuest Investments Ltd": [],
    "Tesco Bank": [],
}


def seed_which_representative(apps, schema_editor):
    """For each TIX, WATCH, or EVOLVE creditor:
      - if row exists with matching creditor_name (case-insensitive),
        update only representative (preserves other fields)
      - if no row exists, create with creditor_name + representative + is_active=True
    For WATCH representatives with trading names, populate trading_names JSONField.
    """
    CreditorCriteria = apps.get_model("debt_app", "CreditorCriteria")

    tix_created = 0
    tix_updated = 0
    watch_created = 0
    watch_updated = 0
    evolve_created = 0
    evolve_updated = 0

    # Seed TIX creditors
    for name in TIX_CREDITORS:
        existing = CreditorCriteria.objects.filter(
            creditor_name__iexact=name
        ).first()
        if existing:
            if existing.representative != "TIX":
                existing.representative = "TIX"
                existing.save(update_fields=["representative"])
            tix_updated += 1
        else:
            CreditorCriteria.objects.create(
                creditor_name=name,
                representative="TIX",
                is_active=True,
            )
            tix_created += 1

    # Seed WATCH representatives
    for rep_name, trading_names in WATCH_REPRESENTATIVES.items():
        existing = CreditorCriteria.objects.filter(
            creditor_name__iexact=rep_name
        ).first()
        if existing:
            updated = False
            if existing.representative != "WATCH":
                existing.representative = "WATCH"
                updated = True
            if trading_names and existing.trading_names != trading_names:
                existing.trading_names = trading_names
                updated = True
            if updated:
                existing.save()
            watch_updated += 1
        else:
            CreditorCriteria.objects.create(
                creditor_name=rep_name,
                representative="WATCH",
                trading_names=trading_names if trading_names else [],
                is_active=True,
            )
            watch_created += 1

    # Seed EVOLVE creditors
    for name in EVOLVE_CREDITORS:
        existing = CreditorCriteria.objects.filter(
            creditor_name__iexact=name
        ).first()
        if existing:
            if existing.representative != "EVOLVE":
                existing.representative = "EVOLVE"
                existing.save(update_fields=["representative"])
            evolve_updated += 1
        else:
            CreditorCriteria.objects.create(
                creditor_name=name,
                representative="EVOLVE",
                is_active=True,
            )
            evolve_created += 1

    print(
        f"  Which Representative seed: "
        f"TIX {tix_created} created {tix_updated} updated, "
        f"WATCH {watch_created} created {watch_updated} updated, "
        f"EVOLVE {evolve_created} created {evolve_updated} updated"
    )


def reverse_which_representative(apps, schema_editor):
    """Clear representative and trading_names on rows that were seeded.
    Does NOT delete rows — they may have other fields populated or be
    referenced by assessment records.
    """
    CreditorCriteria = apps.get_model("debt_app", "CreditorCriteria")

    all_names = (
        TIX_CREDITORS
        + list(WATCH_REPRESENTATIVES.keys())
        + EVOLVE_CREDITORS
    )

    CreditorCriteria.objects.filter(
        creditor_name__in=all_names
    ).update(representative="NONE", trading_names=[])


class Migration(migrations.Migration):
    dependencies = [
        ("debt_app", "0007_alter_creditorcriteria_options_and_more"),
    ]

    operations = [
        migrations.RunPython(
            seed_which_representative,
            reverse_which_representative,
        ),
    ]
