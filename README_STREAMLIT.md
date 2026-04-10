# CMS Template Generator

> Convert localized Word documents into CMS-ready template packages in minutes.

## Quick Start

### Local Development
```bash
git clone https://github.com/federicoiosca87/CRM_TemplatesHandler.git
cd CRM_TemplatesHandler
pip install -r requirements.txt
streamlit run app.py
```

Then visit: http://localhost:8501

### Online (Streamlit Cloud)
Deploy to [Streamlit Community Cloud](https://share.streamlit.io):
1. Sign in with GitHub
2. Select this repo
3. Choose `app.py` as entry point
4. Get your URL (e.g., `https://cms-generator.streamlit.app`)

---

## How It Works

### Step 1: Upload
- **ZIP of Word documents** - One `.docx` per language
  - Format: `{LANGUAGE}_{OfferName}.docx`
  - Example: `EN_MyOffer.docx`, `GR_MyOffer.docx`
- **Images** - PNG/JPG files for OMS templates

### Step 2: Configure Offer
- **Task Type** - PlaceBetWithSettlement, SpinTheWheel, etc.
- **Reward Type** - CashFreespin, BonusBalance, etc.
- **Send Conditions** - When to show to players
- **Template Variants** - A, B, C (or custom)

Auto-detection suggests task/reward type based on content keywords.

### Step 3: Review
- **Quality Reports** - Consistency checks, missing content detection
- **Language Summary** - See what was parsed per language
- **Preview Tab** - Check SMS, OMS, T&Cs before generating

### Step 4: Generate & Download
Three CMS-ready ZIP packages:
- `CampaignWizardSmsTemplate.zip` - SMS templates (all languages)
- `CampaignWizardOmsTemplate.zip` - OMS + images (all languages)
- `CampaignWizardTCTemplate.zip` - Terms & Conditions (all languages)

All packages ready for direct CMS import.

---

## Supported Languages

| Code | Language | Code | Language |
|------|----------|------|----------|
| EN | English | ET | Estonian |
| EN_PE | English (Peru) | FI | Finnish |
| EN_GR | English (Greece) | GR | Greek |
| ARG | Spanish (Argentina) | IS | Icelandic |
| BR | Portuguese (Brazil) | IT | Italian |
| CL | Spanish (Chile) | MX | Spanish (Mexico) |
| CO | Spanish (Colombia) | PE | Spanish (Peru) |
| RU_ET | Russian (Estonia) | DA | Danish |

---

## Word Document Format

Your `.docx` files should contain these sections (in order):

```
MY OFFERS
├── Headline
├── Sub-headline
├── Task
└── Reward

LAUNCH OMS
├── Template A
│   ├── Title
│   ├── Body
│   └── CTA
├── Template B ...
└── Template C ...

REMINDER OMS
└── (same structure)

REWARD RECEIVED – OMS
└── (same structure)

LAUNCH SMS
├── Template A: [body text]
├── Template B: [body text]
└── Template C: [body text]

REMINDER SMS
└── (same structure)

TERMS AND CONDITIONS
├── SIGNIFICANT TERMS (or localized equivalent)
│   └── [key points as bullet points]
└── FULL TERMS (or localized)
    └── [complete T&C text]
```

### Example Section Markers
Recognized in 14+ languages:

**English:** LAUNCH OMS, REMINDER OMS, LAUNCH SMS, REMINDER SMS, TERMS AND CONDITIONS

**Greek:** ΑΡΧΙΚΗ OMS, ΥΠΕΝΘΥΜΙΣΗ OMS, SMS ΕΚΚΙΝΗΣΗΣ, SMS ΥΠΕΝΘΥΜΙΣΗΣ, ΟΡΟΙ ΚΑΙ ΠΡΟΫΠΟΘΕΣΕΙΣ

**Spanish:** LANZAMIENTO OMS, RECORDATORIO OMS, SMS DE LANZAMIENTO, SMS DE RECORDATORIO, TÉRMINOS Y CONDICIONES

**Russian:** ЗАПУСК OMS, НАПОМИНАНИЕ OMS, ЗАПУСК SMS, НАПОМИНАНИЕ SMS, ПРАВИЛА И УСЛОВИЯ

---

## Features

✅ **Multi-language parsing** (14+ languages auto-detected)  
✅ **Auto-detection** of offer type from content keywords  
✅ **Quality reports** - Consistency checks, missing content alerts  
✅ **Bullet list preservation** from Word docs  
✅ **Placeholder validation** - Warns about unknown CW placeholders  
✅ **Localized section markers** in English, Spanish, Portuguese, Greek, Russian, Estonian, Icelandic, Finnish, etc.  
✅ **Image auto-selection** based on reward type  
✅ **Dark mode support** for all previews  
✅ **Live SMS character counter** (160-char and multi-part alerts)  
✅ **Market mapping** - Shows CMS markets for each language  

---

## Valid Campaign Wizard Placeholders

**Common:**
- `%%BrandName%%` - Brand name
- `%%PalantirDomain%%` - SMS link domain
- `%%OfferId%%` - Campaign ID

**Task-related:**
- `%%WagerTaskAmount%%` - Bet amount required
- `%%TaskIncludedBetTypes%%` - Bet types (e.g., "Single or Parlay")
- `%%SBWagerTaskOn%%` - Where to bet (e.g., "Sportsbook")

**Reward-related:**
- `%%NrOfFreespins%%` - Number of free spins
- `%%FreespinGames%%` - Game name
- `%%FreespinValue%%` - Value per spin
- `%%FreespinValidityDays%%` - How many days to use them

**Full reference:** See Campaign Wizard documentation.

---

## Troubleshooting

### "GR: Missing Reminder OMS variants: A, B, C"
- Check Greek Word doc has REMINDER OMS section
- Verify sections use exact markers (case-sensitive)

### "SMS body exceeds 160 chars"
- SMS will be split across multiple messages
- Consider shortening placeholder use or text

### "Unknown placeholder: %%CustomField%%"
- Not a valid Campaign Wizard placeholder
- Check Campaign Wizard documentation or use custom placeholder

### "T&C significant terms not detected"
- Add section header: "SIGNIFICANT TERMS" or localized equivalent
- Example Russian: "ОСНОВНЫЕ ПРАВИЛА"

---

## Development

### File Structure
```
CRM_TemplatesHandler/
├── app.py                 # Main Streamlit dashboard
├── config.py              # Language mappings, placeholders, images
├── word_parser.py         # Parse Word documents
├── xml_generator.py       # Generate CMS XML packages
├── requirements.txt       # Python dependencies
├── images/                # OMS template images (JPG, PNG)
├── ser_files/             # CMS serialized files (binary)
└── README.md             # This file
```

### Key Functions

**word_parser.py:**
- `parse_word_document()` - Extract content from .docx
- `parse_documents_from_folder()` - Batch process ZIP

**config.py:**
- `LANGUAGE_MAPPING` - Map input codes to CMS markets
- `LANGUAGE_NAMES` - Human-readable names
- `SECTION_MARKERS` - Localized section headers
- `OMS_IMAGES` - Available images + CMS IDs

**xml_generator.py:**
- `generate_cms_packages()` - Create CMS-ready ZIPs

**app.py:**
- Auto-detection of offer type
- Quality reports (consistency, completeness)
- Live preview tabs

---

## License

Internal tool for Betsson Group.

---

## Questions?

Contact: [@federicoiosca](https://github.com/federicoiosca87)
