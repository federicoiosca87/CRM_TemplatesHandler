"""
Configuration for CMS Template Generator
"""

# Language mapping: Input filename prefix -> CMS language codes
# Some inputs map to multiple CMS languages (e.g., ARG -> 3 Argentina regions)
LANGUAGE_MAPPING = {
    "EN": ["en"],
    "EN_PE": ["en-pe"],
    "EN_GR": ["en-gr"],
    "EN_EE": ["en-ee"],
    "EN_ET": ["en-ee"],     # EN_ET prefix also maps to English (Estonia)
    "EN_CA": ["en-ca"],     # English (Canada)
    "EN_LV": ["en-lv"],     # English (Latvia)
    "EN_HI": ["en-hi"],     # English (India)
    "EN_BE": ["en-be"],     # English (Belgium)
    "EN_TR": ["en-tr"],
    "ARG": ["es-ar-ba", "es-ar-ca", "es-ar-co"],  # All Argentina regions
    "ARBA": ["es-ar-ba"],   # Argentina Buenos Aires (individual)
    "AR_CABA": ["es-ar-ca"],# Argentina CABA (individual)
    "ARCABA": ["es-ar-ca"], # Argentina CABA (alternate prefix)
    "ARCB": ["es-ar-co"],   # Argentina Córdoba (individual)
    "BR": ["br"],
    "CL": ["cl"],
    "CO": ["co"],
    "DA": ["da"],
    "EL": ["el"],
    "ES": ["es"],
    "ES_XL": ["es_xl"],     # Spanish (Betsson LatAm) - CRS uses underscore
    "ET": ["et"],
    "FI": ["fi"],
    "FR": ["fr"],
    "GR": ["el"],  # Greek uses 'el' code in CMS
    "HI": ["hi"],
    "IS": ["is"],
    "IT": ["it"],
    "LV": ["lv"],
    "MX": ["mx"],
    "NL": ["nl"],
    "NO": ["no"],
    "PE": ["pe"],
    "PL": ["pl"],
    "PY": ["py"],
    "RU": ["ru-ee"],
    "RU_ET": ["ru-ee"],
    "RU_LV": ["ru-lv"],
    "TR": ["tr"],
    "CA": ["en-ca"],
    "COL": ["co"],           # Colombia (alternate code)
    "DK": ["da"],            # Denmark -> Danish
    "ARG_PY": ["py"],        # Argentina+Paraguay shared -> Paraguay CMS code
    "PE_EN": ["en-pe"],      # English for Peru
    "ET_ET": ["et"],         # Estonian for Estonia
    "ET_RU": ["ru-ee"],      # Russian for Estonia
    # Duplicate/brand-specific codes (generated from source copies)
    "EN_AB": ["en-ab"],      # English (ArcticBet) - duplicate from EN
    "EN_BRM": ["en-brm"],    # English (BetSmith) - duplicate from EN
    "EN_BS": ["en-bs"],      # English (BetSolid) - duplicate from EN
}

# Language duplication rules: when a source document is parsed and no dedicated
# document exists for the target code, create a copy from the source.
# This allows reviewing/editing each market's content individually in the QA tab.
LANGUAGE_DUPLICATES = {
    "EN": ["EN_AB", "EN_BRM", "EN_BS", "EN_TR"],  # English brands that use EN copy
    "ARG": ["PY"],        # Paraguay uses ARG copy
    "RU_ET": ["RU_LV"],   # Russian Latvia uses RU_ET copy
}

# Human-readable language names for display
LANGUAGE_NAMES = {
    "EN": "English",
    "EN_PE": "English (Peru)",
    "EN_GR": "English (Greece)",
    "EN_EE": "English (Estonia)",
    "EN_ET": "English (Estonia)",
    "EN_CA": "English (Canada)",
    "EN_LV": "English (Latvia)",
    "EN_HI": "English (India)",
    "EN_BE": "English (Belgium)",
    "EN_TR": "English (Turkey)",
    "ARG": "Spanish (Argentina)",
    "ARBA": "Spanish (Argentina - Buenos Aires)",
    "AR_CABA": "Spanish (Argentina - CABA)",
    "ARCABA": "Spanish (Argentina - CABA)",
    "ARCB": "Spanish (Argentina - Córdoba)",
    "BR": "Portuguese (Brazil)",
    "CL": "Spanish (Chile)",
    "CO": "Spanish (Colombia)",
    "DA": "Danish",
    "EL": "Greek",
    "ES": "Spanish",
    "ES_XL": "Spanish (LatAm)",
    "ET": "Estonian",
    "FI": "Finnish",
    "FR": "French",
    "GR": "Greek",
    "HI": "Hindi",
    "IS": "Icelandic",
    "IT": "Italian",
    "LV": "Latvian",
    "MX": "Spanish (Mexico)",
    "NL": "Dutch",
    "NO": "Norwegian",
    "PE": "Spanish (Peru)",
    "PL": "Polish",
    "PY": "Spanish (Paraguay)",
    "RU": "Russian",
    "RU_ET": "Russian (Estonia)",
    "RU_LV": "Russian (Latvia)",
    "TR": "Turkish",
    "CA": "English (Canada)",
    "COL": "Spanish (Colombia)",
    "DK": "Danish",
    "ARG_PY": "Spanish (Argentina/Paraguay)",
    "PE_EN": "English (Peru)",
    "ET_ET": "Estonian (Estonia)",
    "ET_RU": "Russian (Estonia)",
    # Additional codes from folder names
    "AR": "Spanish (Argentina)",
    "PT": "Portuguese",
    "BT-PT": "Portuguese (Portugal)",
    "BT-BR": "Portuguese (Brazil)",
    "BT-ES": "Spanish (Spain)",
    "BT-IT": "Italian",
    "BT-FI": "Finnish",
    "BT-NO": "Norwegian",
    "BT-DK": "Danish",
    "BT-PL": "Polish",
    "BT-LV": "Latvian",
    "BT-EE": "Estonian",
    "BT-GR": "Greek",
    # Duplicate/brand-specific codes
    "EN_AB": "English (ArcticBet)",
    "EN_BRM": "English (BetSmith)",
    "EN_BS": "English (BetSolid)",
}

# Language to Market mapping for audit report
# Maps language codes to the market(s) they represent
LANGUAGE_TO_MARKET = {
    "EN": "Realm",
    "EN_PE": "Peru",
    "EN_GR": "Greece",
    "EN_EE": "Estonia",
    "EN_ET": "Estonia",
    "EN_CA": "Canada",
    "EN_LV": "Latvia",
    "EN_HI": "India",
    "EN_BE": "Belgium",
    "EN_TR": "Turkey",
    "ARG": "Argentina",
    "ARBA": "Argentina",
    "AR_CABA": "Argentina",
    "ARCABA": "Argentina",
    "ARCB": "Argentina",
    "BR": "Brazil",
    "CL": "Chile",
    "CO": "Colombia",
    "DA": "Sweden",  # Danish speakers in Nordic region
    "EL": "Greece",
    "ES": "Realm",  # Generic Spanish
    "ES_XL": "LatAm",
    "ET": "Estonia",
    "FI": "Finland",
    "FR": "Realm",  # French (generic)
    "GR": "Greece",
    "HI": "India",
    "IS": "Realm",  # Iceland
    "IT": "Italy",
    "LV": "Latvia",
    "MX": "Mexico",
    "NL": "Netherlands",
    "NO": "Norway",
    "PE": "Peru",
    "PL": "Poland",
    "PY": "Paraguay",  # Note: Not in standard markets list, but supported
    "RU": "Estonia",  # Russian speakers
    "RU_ET": "Estonia",
    "RU_LV": "Latvia",
    "TR": "Turkey",
    "CA": "Canada",
    "COL": "Colombia",
    "DK": "Denmark",
    "ARG_PY": "Paraguay",
    "PE_EN": "Peru",
    "ET_ET": "Estonia",
    "ET_RU": "Estonia",
    # Duplicate/brand-specific codes
    "EN_AB": "ArcticBet",
    "EN_BRM": "BetSmith",
    "EN_BS": "BetSolid",
}

# Template types and their content fields
# Hash values are from CMS and must match for import to work
# Updated 2026-04-10 from latest CMS exports
TEMPLATE_TYPES = {
    "SMS": {
        "content_type_name": "CampaignWizardSmsTemplate",
        "fields": ["Body", "TemplateName"],
        "comment": "Campaign Wizard sms communication template",
        "doc_type_id": 5711,
        "ser_file": "sms_ser_file.bin",  # Binary .NET serialized DocumentTypeDescription from CMS export
        "hashes": {
            "ContentTypeHash": "PZfoNS7pU86JAzGrTEoZoTEkkkxZSYjuYopvAUIc7JGb6Uhbb49xHxJYbT9DlniTugZkRp3erCeFMp5SU5g",
            "ContentTypeHeadHash": "hF5hibydf3kzn7nwaWGNZhSrOuUvjyS94LRc3fIa621egypzcV95qf5sRsDqykJIb7NwOjjxYAK0gkBQ0Q7bQ",
            "ContentTypeRulesHash": "2NphhDTFOs7wuW7FJIYKZYbsRubxm1SqX0CXpEkl5tQODD0Fl1gdhW7sKFnzOyXKkYUtwe0jdloSw",
            "ContentTypeMetasHash": "B6xqYnz0FUQS9pYyvPTOc4OWNshTngxPgR4ZYU1UgZeClWmYXepWFzgwccGWyDLNoodxWg6lnkziEMqXw",
            "ContentTypeHeadHashV2": "hH8mvecIzyjeYzLsi5Dad5YoHXrL8jw3bQ0Aqs4d9GdFJfu5rj6rTkPhPQo6y2Zo7Z3jdfKE9ocmpmTgjTPpZg",
        },
    },
    "OMS": {
        "content_type_name": "CampaignWizardOmsTemplate",
        "fields": ["Title", "Body", "CallToAction", "CallToActionMobile", "TemplateName"],
        "comment": "Campaign Wizard oms communication template",
        "doc_type_id": 5712,
        "image_link_data": 1960,
        "ser_file": "oms_ser_file.bin",  # Binary .NET serialized DocumentTypeDescription from CMS export
        "hashes": {
            "ContentTypeHash": "ypk9mQjvEzJPyq9eKL2rXLpyjl1dOaXiCRszNgAhuZFwleSHOadM5EhK8W5ZkLgymYsngTKbulAcBX8VRA",
            "ContentTypeHeadHash": "Hfa9bL3lZiUuJ1uMYVgM8dfdxqVV4AkDoKyocU67nRhQvwyhEHNCX1c1shN4Yjv1WmQPELrRZ2NHVf9S1w",
            "ContentTypeRulesHash": "2XPjemMLtQVHdjUNuQNbypMhH7jZJnLjVWR5IeDCjBDvsueLQfRob1UYUSJviNN86UTXEfp2Ref4OZfOyT8DA",
            "ContentTypeMetasHash": "o0Qhn5EEwVDKp7BVd8PwhcVurJoESbOWwgrcWyR4R4SiYmjhnVORtTGqHP7QgoWludqUuKZ9UgozTgwblg",
            "ContentTypeHeadHashV2": "hH8mvecIzyjeYzLsi5Dad5YoHXrL8jw3bQ0Aqs4d9GdFJfu5rj6rTkPhPQo6y2Zo7Z3jdfKE9ocmpmTgjTPpZg",
        },
    },
    "TC": {
        "content_type_name": "CampaignWizardTCTemplate",
        "fields": ["SignificantTerms", "TermsAndConditions"],
        "comment": "Campaign Wizard TC template",
        "doc_type_id": 3772,
        "ser_file": "tc_ser_file.bin",  # Binary .NET serialized DocumentTypeDescription from CMS export
        "hashes": {
            "ContentTypeHash": "T0bwTHBM7mw3zJd1h4UTTFGmoIJCGvstuGraZaapqq33teU9m7VgfrevFAgxNGVD8RTdoVGWLfEHbZjSWtA",
            "ContentTypeHeadHash": "rEiGFzM0nd4zWT8vJU1KF8Pcv9kYstG4qL8rxNwWf7RCzy11KSWWzqSruUYDrxBzFvlUAXu0MbP1AfhPLV5Yw",
            "ContentTypeRulesHash": "VDiE18HGrN86v99XYTgP98rxEwmPInkXivdMLoKQnOiNJmSP0D4tQPrYB9n2uS2bjGQKp2HavSdycoWyHVolw",
            "ContentTypeMetasHash": "JqPIwd3bq1ivBffwa0g38SMMidhjux4S2MRo2RrCIeMvk8FMWVINWiFOoIUvG5ugoim2kxOJVmSDUhSzb9Xkw",
            "ContentTypeHeadHashV2": "hH8mvecIzyjeYzLsi5Dad5YoHXrL8jw3bQ0Aqs4d9GdFJfu5rj6rTkPhPQo6y2Zo7Z3jdfKE9ocmpmTgjTPpZg",
        },
    },
    "PUSH": {
        "content_type_name": "CampaignWizardPushNotificationTemplate",
        "fields": ["Title", "Body", "ActionKey", "ActionValue", "TemplateName"],
        "comment": "Campaign Wizard push notification communication template",
        "doc_type_id": 3787,
        "image_link_data": 1931,
        "ser_file": "push_ser_file.bin",
        "hashes": {
            "ContentTypeHash": "YssuSYCyZDpDO8EUvXqj85jf4HLDU4loGUuOEe3CLsyvT1a6LnZwT830aWooZFbjy6o4ymHPc4y14VVTd3g",
            "ContentTypeHeadHash": "ilgkB2LPlWiGgrrgOETN4RgkVJlehYEaffqZ1shiYhtRaeS8sfJjf7K9D9mp4KCzQK7Oa6hp0EjE6ViFGZQ",
            "ContentTypeRulesHash": "2KJNiAzOQuiZ22VZv9CVb0XnP2xFdoXeZ0RwJNN3QS51OC85RB1sOR8SAZkdmqArdkwrXzGtEpg3YR7Ph9w",
            "ContentTypeMetasHash": "x3Zx1Kg5X7OUVEEtAeNz03txjVud7R9VxCkUaja3mTkkNEMjhkkIRdw90aNgpEJoTKjFtlUFugOMnlW6pmKg",
            "ContentTypeHeadHashV2": "hH8mvecIzyjeYzLsi5Dad5YoHXrL8jw3bQ0Aqs4d9GdFJfu5rj6rTkPhPQo6y2Zo7Z3jdfKE9ocmpmTgjTPpZg",
        },
    },
}

# Word document section markers (headings that identify content sections)
# These patterns help parse the Word document structure
SECTION_MARKERS = {
    "MY_OFFERS": ["MY OFFERS", "MYOFFERS"],
    "LAUNCH_OMS": ["LAUNCH OMS", "LAUNCH"],
    "REMINDER_OMS": ["REMINDER OMS", "OMS REMINDER", "REMINDER"],
    "REWARD_OMS": [
        # English
        "REWARD RECEIVED", "REWARD RECEIVED OMS", "REWARD OMS",
        # Spanish (ES, AR, PE, MX, CO, CL)
        "RECOMPENSA RECIBIDA",
        # Portuguese (BR, PT)
        "RECOMPENSA RECEBIDA",
        # German
        "BELOHNUNG ERHALTEN",
        # Italian
        "RICOMPENSA RICEVUTA",
        # French
        "RÉCOMPENSE REÇUE", "RECOMPENSE RECUE",
        # Finnish
        "PALKINTO VASTAANOTETTU",
        # Greek
        "ΕΠΙΒΡΑΒΕΥΣΗ", "ΑΝΤΑΜΟΙΒΗ",
        # Russian
        "НАГРАДА ПОЛУЧЕНА",
        # Swedish
        "BELÖNING MOTTAGEN",
        # Norwegian
        "BELØNNING MOTTATT",
        # Danish
        "BELØNNING MODTAGET",
        # Polish
        "NAGRODA OTRZYMANA",
        # Turkish
        "ÖDÜL ALINDI",
    ],
    "LAUNCH_SMS": [
        "LAUNCH SMS", "SMS LAUNCH",
        "SMS - LAUNCH",  # BR dash format
        "СМС LAUNCH", "LAUNCH СМС",  # Russian Cyrillic
        # Greek
        "SMS ΕΚΚΙΝΗΣΗΣ", "SMS ΑΠΟΣΤΟΛΗΣ", "ΑΡΧΙΚΟ SMS",
        # Spanish
        "SMS DE LANZAMIENTO", "SMS LANZAMIENTO",
        # Portuguese
        "SMS DE LANÇAMENTO",
        # German
        "SMS START", "START SMS",
        # Italian
        "SMS DI LANCIO",
        # French
        "SMS DE LANCEMENT",
        # Estonian
        "LANSSEERIMINE",
    ],
    "REMINDER_SMS": [
        "REMINDER SMS", "SMS REMINDER",
        "SMS - REMINDER",  # BR dash format
        "СМС REMINDER", "REMINDER СМС",  # Russian Cyrillic
        # Greek
        "SMS ΥΠΕΝΘΥΜΙΣΗΣ", "ΥΠΕΝΘΥΜΙΣΤΙΚΟ SMS",
        # Spanish
        "SMS DE RECORDATORIO", "SMS RECORDATORIO",
        # Portuguese
        "SMS DE LEMBRETE",
        # German
        "SMS ERINNERUNG", "ERINNERUNG SMS",
        # Italian
        "SMS DI PROMEMORIA",
        # French
        "SMS DE RAPPEL",
        # Estonian
        "MEELDETULETUS",
    ],
    "SMS": [
        "SMS", "SMS TEMPLATES", "LAUNCH SMS", "REMINDER SMS",
        # Greek
        "SMS ΕΚΚΙΝΗΣΗΣ", "SMS ΥΠΕΝΘΥΜΙΣΗΣ",
        # Spanish
        "SMS DE LANZAMIENTO", "SMS DE RECORDATORIO",
    ],
    "LAUNCH_PUSH": [
        "LAUNCH PUSH", "PUSH LAUNCH", "LAUNCH PUSH NOTIFICATION",
        "PUSH NOTIFICATION LAUNCH", "PUSH NOTIFICATION - LAUNCH",
    ],
    "REMINDER_PUSH": [
        "REMINDER PUSH", "PUSH REMINDER", "REMINDER PUSH NOTIFICATION",
        "PUSH NOTIFICATION REMINDER", "PUSH NOTIFICATION - REMINDER",
    ],
    "REWARD_PUSH": [
        "REWARD PUSH", "PUSH REWARD", "REWARD PUSH NOTIFICATION",
        "PUSH NOTIFICATION REWARD", "PUSH NOTIFICATION - REWARD",
        "REWARD RECEIVED PUSH", "PUSH REWARD RECEIVED",
        "REWARD RECEIVED - PUSH", "REWARD RECEIVED – PUSH",
        "CLAIMED REWARD PUSH", "PUSH CLAIMED REWARD",
    ],
    "TC": [
        # English
        "T&C", "T&CS", "TAC", "TERMS", "TERMS AND CONDITIONS", "SIGNIFICANT TERMS",
        "TERMS & CONDITIONS",  # Variant with ampersand
        # Greek
        "ΟΡΟΙ ΚΑΙ ΠΡΟΫΠΟΘΕΣΕΙΣ", "ΣΗΜΑΝΤΙΚΟΙ ΟΡΟΙ", "ΠΛΗΡΕΙΣ ΟΡΟΙ", "ΟΡΟΙ",
        # Spanish
        "TÉRMINOS Y CONDICIONES", "CONDICIONES IMPORTANTES", "CONDICIONES",
        # Portuguese
        "TERMOS E CONDIÇÕES", "TERMOS IMPORTANTES", "TERMOS",
        # German
        "ALLGEMEINE GESCHÄFTSBEDINGUNGEN", "GESCHÄFTSBEDINGUNGEN", "BEDINGUNGEN", "AGB",
        # Italian
        "TERMINI E CONDIZIONI", "CONDIZIONI", "TERMINI",
        # French
        "CONDITIONS GÉNÉRALES", "TERMES ET CONDITIONS", "CONDITIONS",
        # Finnish
        "KÄYTTÖEHDOT", "EHDOT", "YLEISET EHDOT",
        # Russian
        "УСЛОВИЯ", "ПРАВИЛА И УСЛОВИЯ",
        # Swedish
        "VILLKOR", "ALLMÄNNA VILLKOR",
        # Norwegian
        "VILKÅR", "BETINGELSER",
        "BETINGELSER OG VILKÅR", "VIKTIGE BETINGELSER OG VILKÅR",
        # Danish
        "VILKÅR OG BETINGELSER", "BETINGELSER",
        # Polish
        "REGULAMIN", "WARUNKI", "WARUNKI I ZASADY", "ISTOTNE WARUNKI I ZASADY",
        # Turkish
        "ŞARTLAR VE KOŞULLAR", "KOŞULLAR", "ŞARTLAR & KOŞULLAR",
        "ÖNEMLI ŞARTLAR VE KOŞULLAR",  # Turkish "Important Terms"
        # Estonian
        "TINGIMUSED", "OLULISED TINGIMUSED", "TÄIELIKUD TINGIMUSED",
        "REEGLID JA TINGIMUSED", "REEGLID",
        # Latvian
        "NOTEIKUMI", "BŪTISKIE NOTEIKUMI",
        # Icelandic
        "REGLUR OG SKILYRÐI", "SKILYRÐI",
    ],
}

# Template variants available
TEMPLATE_VARIANTS = ["A", "B", "C", "D", "E", "F"]

# Send conditions (communication statuses)
SEND_CONDITIONS = {
    "NotOptedIn": "NotOptedIn",
    "JoinedCampaign": "JoinedCampaign",
    "CampaignHasStarted": "CampaignHasStarted",
    "Apology": "Apology",
    "ClaimedReward-TemplateA": "ClaimedReward-TemplateA",
    "ClaimedReward-TemplateB": "ClaimedReward-TemplateB",
}

# Task types available in CW
# Note: Custom task types can also be entered in the UI via "➕ Custom..."
# Add new permanent types here if they become standard
TASK_TYPES = [
    "OptIn",
    "Deposit",
    "Wager",
    "WagerSportsbookWithSettlement",
    "WagerSportsbookWithoutSettlement",
    "PlaceBetWithSettlement",
    "PlaceBetWithoutSettlement",
    "NetLossGameplay",
    "NetLossSportsbook",
]

# Reward types available in CW
# Note: Custom reward types can also be entered in the UI via "➕ Custom..."
# Add new permanent types here if they become standard
REWARD_TYPES = [
    "Freespin",
    "CashFreespin",
    "BonusMoney",
    "CashMoney",
    "FixedBonusAmount",
    "BonusFreeBet",
    "CashFreeBet",
    "BonusRiskFreeBet",
    "CashRiskFreeBet",
    "BonusBack",
    "CashBack",
]

# Bonus product options (for some offer types)
# These values must match exactly what CRS uses
BONUS_PRODUCTS = [
    "AllProducts",
    "CasinoExcludeLiveCasino",
    "CasinoIncludeLiveCasino",
    "LiveCasino",
    "Sportsbook",
]

# OMS Image options - maps display name to (CMS key, CMS ID, filename)
# These are brand-agnostic images from GenericSiteMessageImageRepository in CMS (Production)
OMS_IMAGES = {
    "Bonus Free Spin (Casino)": ("CW_BonusFreeSpin_casino", "3736707", "6f9506db0ced4118993357b114c831ce.jpg"),
    "Cash Free Spin (Casino)": ("CW_CashFreeSpin_casino", "3737033", "4f14c09c94504fb2aa35dc6bf38a778b.jpg"),
    "Bonus Free Bet (Sportsbook)": ("CW_BonusFreeBet_SB", "3737043", "35e1b172edff47088084c6dd470d7417.jpg"),
    "Cash Free Bet (Sportsbook)": ("CW_CashFreeBet_SB", "3731833", "312a441496df4215ac74c0b94d6b8a6f.jpg"),
    "Bonus Risk Free Bet (Sportsbook)": ("CW_BonusRiskFreeBet_SB", "3733425", "e779d53c7d6147c086d46ed47e65be34.jpg"),
    "Cash Risk Free Bet (Sportsbook)": ("CW_CashRiskFreeBet_SB", "3733479", "7b1137b2673243319d3c7eeb3cb4938a.jpg"),
    "Bonus Money (Sportsbook)": ("CW_BonusMoney_SB", "3839232", "b32884b2f49e4310a95038e5a36d342e.jpg"),
    "Bonus Money (Casino)": ("CW_BonusMoney_casino", "3836846", "4c867329b9dd4b85afcdc17256a98faf.jpg"),
    "Cash Money (Casino)": ("CW_CashMoney_CA", "4063536", "4add4021764140b0b2c6b96f26daf14b.jpg"),
    "Live Casino - Wager&Get Bonus A": ("CW_wager_BonusMoney_LiveCasino", "3972223", "d0167fa741c94cd989e56086c273bc1f.jpg"),
    "Live Casino - Wager&Get Bonus B": ("CW_wager_BonusMoney_LiveCasino_B", "4372579", "001323f12c6c4c50b4927803f67f3aae.jpg"),
    "Live Casino - Wager&Get Bonus C": ("CW_wager_BonusMoney_LiveCasino_C", "4373021", "2f42afa5555f4ae88374ac4616fdec88.jpg"),
    "Default Image 1": ("CampaignWizardDefaultImage1", "3074626", "99a4119e9a144e468c05072f345a9f91.png"),
}

# SMS character limits (for validation)
SMS_MAX_LENGTH = 320  # 2 SMS segments

# Default CMS XML attributes
CMS_DEFAULTS = {
    "Merchant": "Common",
    "Brand": "Common",
    "Product": "Common",
    "ServiceInstanceName": "AdminInstance",
    "ServiceInstanceId": "2",
    "ServiceVersion": "3.4.4.0",
    "ContentTypeMerchant": "Common",
    "ContentTypeBrand": "Common",
    "ContentTypeProduct": "Common",
}

# Validation Rules by Brand
# Define per-brand placeholder restrictions. Each rule:
# - key: placeholder token name (without %% markers)
# - value: dict with:
#   - allowed_contexts: tuple of field types where this token is allowed ("sms", "oms_title", "oms_body", "tc")
#   - reason: brief explanation of the rule
#
# Example: FreespinValue is never allowed in SMS for Brand X due to compliance
BRAND_VALIDATION_RULES = {
    "BrandX": {
        "FreespinValue": {
            "allowed_contexts": ("oms_title", "oms_body", "tc"),
            "reason": "SMS context restricted per compliance review (Dec 2025)",
        },
        "BonusAmount": {
            "allowed_contexts": ("oms_body", "tc"),
            "reason": "Do not advertise bonus amount in title or SMS (brand positioning)",
        },
    },
    "BrandY": {
        "WagerTaskAmount": {
            "allowed_contexts": ("oms_title", "oms_body"),
            "reason": "SMS not used for wager terms (T&Cs only)",
        },
    },
    # Add more brands as validation rules are defined
}
