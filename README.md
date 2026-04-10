# CMS Template Generator

A local dashboard tool for converting localized Word documents into CMS-ready template packages.

## Use Case

> "As a user, I want to upload a ZIP folder of localized content and images into the dashboard, and download 3 separate ZIPs ready for CMS import: one for OMS templates, one for SMS templates, and one for Terms & Conditions."

## Problem Solved

**Before:** Content team manually copies content from Word docs into CMS for each language and template variant. Takes ~1 month per offer type.

**After:** Upload ZIP + images, configure offer metadata, download 3 CMS-ready packages. Takes ~5 minutes.

## Features

- 📄 **Upload localized content** - ZIP containing Word documents
- 🖼️ **Upload images** - For OMS/CRS templates  
- ⚙️ **Configure offer** - Task type, reward type, send conditions, variants
- 🔧 **Custom types** - Add new task/reward types on the fly
- 👁️ **Preview content** - Verify extracted content before generating
- 📥 **Download 3 packages** - SMS, OMS (with images), TC - all CMS-ready

## Workflow

```
┌─────────────────────────────────────────────────────────────┐
│  1. UPLOAD                                                  │
│  ├── ZIP with Word docs ({LANG}_{OfferName}.docx)          │
│  └── Images (PNG, JPG, etc.)                               │
├─────────────────────────────────────────────────────────────┤
│  2. CONFIGURE (sidebar)                                     │
│  ├── Task Type (or custom)                                 │
│  ├── Reward Type (or custom)                               │
│  ├── Send Conditions                                        │
│  └── Template Variants (A-F)                               │
├─────────────────────────────────────────────────────────────┤
│  3. PREVIEW                                                 │
│  ├── SMS templates per language                            │
│  ├── OMS templates per language                            │
│  └── T&Cs                                                   │
├─────────────────────────────────────────────────────────────┤
│  4. DOWNLOAD                                                │
│  ├── 📦 CampaignWizardSmsTemplate.zip                      │
│  ├── 📦 CampaignWizardOmsTemplate.zip (+ images)           │
│  └── 📦 CampaignWizardTCTemplate.zip                       │
└─────────────────────────────────────────────────────────────┘
```

## Input Format

ZIP file containing Word documents with naming: `{LANGUAGE}_{OfferName}.docx`

Example:
```
Bet&Get_CashFreespin.zip
└── Sett. Bet & Cash Free Spins -- 1550/
    ├── EN_bet_on_sb_get_CFS.docx
    ├── BR_bet_on_sb_get_CFS.docx
    ├── ARG_bet_on_sb_get_CFS.docx
    └── ...
```

### Word Document Structure

The parser expects these sections (identified by headings):

| Section | Content |
|---------|---------|
| MY OFFERS | Headline, Sub-headline, Task, Reward |
| LAUNCH OMS | Template A/B/C: Title, Body, CTA |
| REMINDER OMS | Template A/B/C: Title, Body, CTA |
| SMS | Template A-F: Body |
| T&Cs/SIGNIFICANT TERMS | SignificantTerms, TermsAndConditions |

## Output Format

Three CMS-compatible ZIP packages:

1. `MultiMCmsExport_CampaignWizardSmsTemplate_{date}_common_common_all.zip`
2. `MultiMCmsExport_CampaignWizardOmsTemplate_{date}_common_common_all.zip`
3. `MultiMCmsExport_CampaignWizardTCTemplate_{date}_common_common_all.zip`

**SMS & TC Structure:**
```
Common/
├── ContentTypeList.txt
├── DocumentTypeList.txt
└── CampaignWizard{Type}Template/
    ├── en/
    │   ├── ContentList.xml
    │   └── DocumentList.xml
    ├── br/
    └── ...
```

**OMS Structure (includes images):**
```
Common/
├── ContentTypeList.txt
├── DocumentTypeList.txt
└── CampaignWizardOmsTemplate/
    ├── files/              ← Uploaded images
    │   ├── banner.png
    │   └── promo.jpg
    ├── en/
    │   ├── ContentList.xml
    │   └── DocumentList.xml
    └── ...
```

## Installation

```bash
# Navigate to tool directory
cd tools/cms-template-generator

# Create virtual environment (recommended)
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Mac/Linux

# Install dependencies
pip install -r requirements.txt
```

## Usage

```bash
# Start the dashboard
streamlit run app.py
```

The app will open in your browser at http://localhost:8501

### Steps:

1. **Configure Offer** (sidebar)
   - Select Task Type (or "➕ Custom..." for new types)
   - Select Reward Type (or "➕ Custom..." for new types)
   - Choose Send Conditions (NotOptedIn, JoinedCampaign, etc.)
   - Select Template Variants (A, B, C, D, E, F)

2. **Upload Content**
   - Upload ZIP file with Word documents
   - Upload images for OMS/CRS templates (optional)
   - Review the parsed document summary

3. **Preview**
   - See uploaded images
   - Select a language to inspect extracted content
   - Verify SMS, OMS, and T&C content

4. **Generate & Download**
   - Review configuration summary
   - Click "Generate CMS Packages"
   - Download 3 packages:
     - 📦 SMS Package
     - 📦 OMS Package (includes images)
     - 📦 TC Package

5. **Import to CMS**
   - Upload each package to CMS admin interface

## Language Mapping

| Input (Word) | CMS Code(s) | Notes |
|--------------|-------------|-------|
| EN | en | Base English |
| EN_PE | en-pe | English (Peru) |
| ARG | es-ar-ba, es-ar-ca, es-ar-co | All Argentina regions |
| BR | br | Brazilian Portuguese |
| GR | el | Greek (different code!) |
| ET | et | Estonian |
| RU_ET | ru-ee | Russian (Estonia) |
| ... | ... | See config.py for full list |

## Configuration

Edit `config.py` to:
- Add/modify language mappings
- Update task types and reward types
- Adjust template variants
- Change CMS metadata defaults

## Troubleshooting

### "No Word documents found in ZIP"
- Ensure ZIP contains .docx files (not .doc)
- Check for nested folders in the ZIP

### Missing sections in preview
- Verify Word document has expected section headings (SMS, LAUNCH OMS, etc.)
- Check for typos in section headers

### XML validation errors on CMS import
- Ensure all required fields have content
- Check for special characters that need escaping

## Files

| File | Purpose |
|------|---------|
| `app.py` | Streamlit dashboard UI |
| `config.py` | Configuration (languages, types, metadata) |
| `word_parser.py` | Word document parsing logic |
| `xml_generator.py` | CMS XML generation |
| `requirements.txt` | Python dependencies |

## Future Improvements

- [ ] CSV input support (alternative to Word docs)
- [ ] Validation rules (SMS character limits, required fields)
- [ ] Direct CMS API integration (skip ZIP download)
- [ ] Template diff viewer (compare with existing CMS content)
- [ ] Batch processing (multiple offer types at once)
