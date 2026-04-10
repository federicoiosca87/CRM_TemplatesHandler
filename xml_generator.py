"""
CMS XML Generator for Campaign Wizard Templates

Generates CMS-compatible XML files for SMS, OMS, and TC templates.
"""

import hashlib
import random
import string
from datetime import datetime
from pathlib import Path
from typing import Optional
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom

from config import (
    LANGUAGE_MAPPING,
    TEMPLATE_TYPES,
    CMS_DEFAULTS,
    SMS_MAX_LENGTH,
)
from word_parser import ParsedDocument, TemplateContent


def _generate_hash(length: int = 64) -> str:
    """Generate a random hash-like string for CMS compatibility."""
    chars = string.ascii_letters + string.digits
    return ''.join(random.choices(chars, k=length))


def _generate_content_id() -> int:
    """Generate a unique content ID."""
    return random.randint(9000000, 9999999)


def _generate_item_id() -> int:
    """Generate a unique content item ID."""
    return random.randint(120000000, 129999999)


def _escape_xml_content(text: str) -> str:
    """Escape special characters for XML content."""
    if not text:
        return ""
    # Handle common formatting


def _generate_description_txt(content_type_name: str, hashes: dict) -> str:
    """Generate ContentTypeDescription.txt / DocumentTypeDescription.txt content."""
    return ";".join([
        content_type_name,
        hashes.get("ContentTypeHash", ""),
        hashes.get("ContentTypeHeadHash", ""),
        hashes.get("ContentTypeRulesHash", ""),
        hashes.get("ContentTypeMetasHash", ""),
        hashes.get("ContentTypeHeadHashV2", ""),
    ])


def _generate_content_type_description_xml(content_type_name: str, comment: str, doc_type_id: int) -> str:
    """Generate ContentTypeDescription.xml content."""
    return f'''<DocumentType xmlns="http://schemas.datacontract.org/2004/07/Content.Service.BusinessEntities" xmlns:i="http://www.w3.org/2001/XMLSchema-instance"><AccessLevelId>0</AccessLevelId><AccessLevelName>ContentManager</AccessLevelName><AccessLevelUserGroup>Content</AccessLevelUserGroup><AppendToTop>false</AppendToTop><CanAdd>true</CanAdd><Comment>{comment}</Comment><DateTimeMode>0</DateTimeMode><DocumentCount>0</DocumentCount><DocumentRuleList i:nil="true"/><DocumentTypeContextDescription i:nil="true"/><EnableActiveToggle>true</EnableActiveToggle><EnableForLobby>false</EnableForLobby><EnableKeyDisplay>true</EnableKeyDisplay><EnableRemark>false</EnableRemark><Enabled>true</Enabled><EnforceDateTime>false</EnforceDateTime><Icon/><Id>{doc_type_id}</Id><LastModifiedDateTime i:nil="true"/><LastModifiedUserName i:nil="true"/><LocalDocumentCount>0</LocalDocumentCount><MandatoryKey>true</MandatoryKey><MarketList i:nil="true" xmlns:a="http://schemas.datacontract.org/2004/07/System"/><MarketListString i:nil="true"/><MarketSelectMode>0</MarketSelectMode><MetaLinkedCount>0</MetaLinkedCount><Name>{content_type_name}</Name><PreviewUrl/><PriorityMaxValue>0</PriorityMaxValue><ProductId>1001</ProductId><ProfileSelectMode>0</ProfileSelectMode><SortMode>0</SortMode><SortOrder>0</SortOrder><_accessType i:nil="true"/></DocumentType>'''


def _generate_document_type_description_xml(content_type_name: str, comment: str, doc_type_id: int, template_type: str, image_link_data: int = 1960) -> str:
    """Generate DocumentTypeDescription.xml content with DocumentMetaList matching CMS exactly."""
    # Define metadata fields based on template type - must match CMS internal definition exactly
    if template_type == "OMS":
        # OMS has: image (linked), rewardType, taskType, sendCondition, bonusProduct
        meta_list = f'''<DocumentMetaList><DocumentMeta IsBoolean="False" IsLink="True" IsList="False"><Key>image</Key><Active>True</Active><LinkData>{image_link_data}</LinkData><MinCount>1</MinCount><MaxCount>1</MaxCount><SortOrder>0</SortOrder></DocumentMeta>
<DocumentMeta IsBoolean="False" IsLink="False" IsList="True"><Key>rewardType</Key><Active>True</Active><LinkData></LinkData><MinCount>1</MinCount><MaxCount>1</MaxCount><SortOrder>1</SortOrder></DocumentMeta>
<DocumentMeta IsBoolean="False" IsLink="False" IsList="True"><Key>taskType</Key><Active>True</Active><LinkData></LinkData><MinCount>1</MinCount><MaxCount>1</MaxCount><SortOrder>2</SortOrder></DocumentMeta>
<DocumentMeta IsBoolean="False" IsLink="False" IsList="True"><Key>sendCondition</Key><Active>True</Active><LinkData></LinkData><MinCount>1</MinCount><MaxCount>1</MaxCount><SortOrder>3</SortOrder></DocumentMeta>
<DocumentMeta IsBoolean="False" IsLink="False" IsList="True"><Key>bonusProduct</Key><Active>True</Active><LinkData></LinkData><MinCount>1</MinCount><MaxCount>1</MaxCount><SortOrder>4</SortOrder></DocumentMeta>
</DocumentMetaList>'''
    elif template_type == "SMS":
        # SMS has: rewardType, taskType, sendCondition
        meta_list = '''<DocumentMetaList><DocumentMeta IsBoolean="False" IsLink="False" IsList="True"><Key>rewardType</Key><Active>True</Active><LinkData></LinkData><MinCount>1</MinCount><MaxCount>1</MaxCount><SortOrder>0</SortOrder></DocumentMeta>
<DocumentMeta IsBoolean="False" IsLink="False" IsList="True"><Key>taskType</Key><Active>True</Active><LinkData></LinkData><MinCount>1</MinCount><MaxCount>1</MaxCount><SortOrder>1</SortOrder></DocumentMeta>
<DocumentMeta IsBoolean="False" IsLink="False" IsList="True"><Key>sendCondition</Key><Active>True</Active><LinkData></LinkData><MinCount>1</MinCount><MaxCount>1</MaxCount><SortOrder>2</SortOrder></DocumentMeta>
</DocumentMetaList>'''
    else:  # TC
        # TC has: rewardType, taskType
        meta_list = '''<DocumentMetaList><DocumentMeta IsBoolean="False" IsLink="False" IsList="True"><Key>rewardType</Key><Active>True</Active><LinkData></LinkData><MinCount>1</MinCount><MaxCount>1</MaxCount><SortOrder>0</SortOrder></DocumentMeta>
<DocumentMeta IsBoolean="False" IsLink="False" IsList="True"><Key>taskType</Key><Active>True</Active><LinkData></LinkData><MinCount>1</MinCount><MaxCount>1</MaxCount><SortOrder>1</SortOrder></DocumentMeta>
</DocumentMetaList>'''
    
    return f'''<DocumentType Merchant="Common" Brand="Common" Product="Common" xmlns="http://schemas.datacontract.org/2004/07/Content.Service.BusinessEntities" xmlns:i="http://www.w3.org/2001/XMLSchema-instance"><AccessLevelId>0</AccessLevelId><AccessLevelName>ContentManager</AccessLevelName><AccessLevelUserGroup>Content</AccessLevelUserGroup><AppendToTop>false</AppendToTop><CanAdd>true</CanAdd><Comment>{comment}</Comment><DateTimeMode>0</DateTimeMode><DocumentCount>0</DocumentCount><DocumentRuleList i:nil="true"/><DocumentTypeContextDescription i:nil="true"/><EnableActiveToggle>true</EnableActiveToggle><EnableForLobby>false</EnableForLobby><EnableKeyDisplay>true</EnableKeyDisplay><EnableRemark>false</EnableRemark><Enabled>true</Enabled><EnforceDateTime>false</EnforceDateTime><Icon/><Id>{doc_type_id}</Id><LastModifiedDateTime i:nil="true"/><LastModifiedUserName i:nil="true"/><LocalDocumentCount>0</LocalDocumentCount><MandatoryKey>true</MandatoryKey><MarketList i:nil="true" xmlns:a="http://schemas.datacontract.org/2004/07/System"/><MarketListString i:nil="true"/><MarketSelectMode>0</MarketSelectMode><MetaLinkedCount>0</MetaLinkedCount><Name>{content_type_name}</Name><PreviewUrl/><PriorityMaxValue>0</PriorityMaxValue><ProductId>1001</ProductId><ProfileSelectMode>0</ProfileSelectMode><SortMode>0</SortMode><SortOrder>0</SortOrder><_accessType i:nil="true"/>{meta_list}</DocumentType>'''


def _format_cms_text(text: str) -> str:
    """Format text for CMS (convert markdown-like to CMS BBCode)."""
    if not text:
        return ""
    
    # Convert bullet points
    lines = text.split("\n")
    in_list = False
    formatted_lines = []
    
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("•") or stripped.startswith("-") or stripped.startswith("*"):
            if not in_list:
                formatted_lines.append("[ul]")
                in_list = True
            content = stripped.lstrip("•-* ").strip()
            formatted_lines.append(f"[li]{content}[/li]")
        else:
            if in_list:
                formatted_lines.append("[/ul]")
                in_list = False
            formatted_lines.append(stripped)
    
    if in_list:
        formatted_lines.append("[/ul]")
    
    return "\n".join(formatted_lines)


class CmsXmlGenerator:
    """Generator for CMS-compatible XML template files."""
    
    # Default placeholder image key - can be overridden per offer
    DEFAULT_IMAGE_KEY = "CW_BonusFreeSpin_casino"
    DEFAULT_IMAGE_ID = "3736707"
    
    def __init__(
        self,
        offer_key: str,
        task_type: str,
        reward_type: str,
        send_conditions: list[str],
        variants: list[str],
        bonus_product: Optional[str] = None,
        image_key: Optional[str] = None,
        image_id: Optional[str] = None,
    ):
        """
        Initialize the generator with offer configuration.
        
        Args:
            offer_key: The offer type key (e.g., "PlaceBetWithSettlement-CashFreeSpins")
            task_type: Task type for metadata
            reward_type: Reward type for metadata
            send_conditions: List of send conditions to generate
            variants: List of template variants (A, B, C, etc.)
            bonus_product: Optional bonus product for metadata
            image_key: Optional image key for OMS templates (e.g., "CW_BonusFreeSpin_casino")
            image_id: Optional CMS content ID for the image (e.g., "3736707")
        """
        self.offer_key = offer_key
        self.task_type = task_type
        self.reward_type = reward_type
        self.send_conditions = send_conditions
        self.variants = variants
        self.bonus_product = bonus_product
        self.image_key = image_key or self.DEFAULT_IMAGE_KEY
        self.image_id = image_id or self.DEFAULT_IMAGE_ID
        self.generated_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def _create_content_list_element(self, content_type_name: str, market: str) -> Element:
        """Create the root ContentList element with all attributes."""
        # Find the template type config to get proper hashes
        template_config = None
        for ttype, config in TEMPLATE_TYPES.items():
            if config["content_type_name"] == content_type_name:
                template_config = config
                break
        
        hashes = template_config.get("hashes", {}) if template_config else {}
        
        root = Element("ContentList")
        root.set("ContentTypeName", content_type_name)
        root.set("ContentTypeHash", hashes.get("ContentTypeHash", _generate_hash(86)))
        root.set("ContentTypeHeadHash", hashes.get("ContentTypeHeadHash", _generate_hash(86)))
        root.set("ContentTypeRulesHash", hashes.get("ContentTypeRulesHash", _generate_hash(86)))
        root.set("ContentTypeMetasHash", hashes.get("ContentTypeMetasHash", _generate_hash(86)))
        root.set("ContentTypeHeadHashV2", hashes.get("ContentTypeHeadHashV2", _generate_hash(86)))
        root.set("Merchant", CMS_DEFAULTS["Merchant"])
        root.set("Brand", CMS_DEFAULTS["Brand"])
        root.set("Product", CMS_DEFAULTS["Product"])
        root.set("Generated", self.generated_time)
        root.set("Market", market)
        root.set("ServiceInstanceName", CMS_DEFAULTS["ServiceInstanceName"])
        root.set("ServiceInstanceId", CMS_DEFAULTS["ServiceInstanceId"])
        root.set("ServiceVersion", CMS_DEFAULTS["ServiceVersion"])
        root.set("ContentTypeMerchant", CMS_DEFAULTS["ContentTypeMerchant"])
        root.set("ContentTypeBrand", CMS_DEFAULTS["ContentTypeBrand"])
        root.set("ContentTypeProduct", CMS_DEFAULTS["ContentTypeProduct"])
        return root
    
    def _create_content_element(
        self,
        content_type_name: str,
        key: str,
        content_items: list[tuple[str, str, str]],  # (rule_name, type_name, data)
        metadata: dict[str, str],
        include_image: bool = False,
    ) -> Element:
        """
        Create a Content element with items and metadata.
        
        Args:
            content_type_name: The content type (e.g., CampaignWizardSmsTemplate)
            key: The content key
            content_items: List of (rule_name, type_name, data) tuples
            metadata: Dictionary of metadata key-value pairs
            include_image: Whether to include image metadata (for OMS templates)
        """
        content = Element("Content")
        content.set("Id", str(_generate_content_id()))
        content.set("Key", key)
        content.set("Active", "True")
        content.set("UpdateInfoUserName", "CMS Template Generator")
        content.set("UpdateInfoDateTime", self.generated_time)
        
        # Add standard sub-elements
        SubElement(content, "Priority").text = "0"
        SubElement(content, "PublishStartDate")
        SubElement(content, "PublishEndDate")
        SubElement(content, "Remark")
        SubElement(content, "SortOrder").text = "1"
        SubElement(content, "ContentMarketList")
        SubElement(content, "ContentProfileList")
        
        # Add content items
        item_list = SubElement(content, "ContentItemList")
        rule_id = 14700
        for rule_name, type_name, data in content_items:
            item = SubElement(item_list, "ContentItem")
            item.set("Id", str(_generate_item_id()))
            item.set("RestrictionBool", "False")
            item.set("RestrictionX", "0")
            item.set("RestrictionY", "0")
            item.set("ContentRuleName", rule_name)
            item.set("DocumentRuleName", rule_name)
            item.set("TypeName", type_name)
            item.set("ContentRuleId", str(rule_id))
            item.set("DocumentRuleId", str(rule_id))
            rule_id += 1
            
            elem_list = SubElement(item, "ContentElementList")
            elem = SubElement(elem_list, "ContentElement")
            # Map internal type names to CMS ContentElement TypeName
            # For Button items, the text element uses TypeName="Text" (not "Button")
            # Only PlainText and Button map to "Text", others stay as-is
            elem_type = "Text" if type_name in ("PlainText", "Button") else type_name
            elem.set("TypeName", elem_type)
            elem.set("IsFile", "False")
            elem.set("MetaDataRaw", "")
            SubElement(elem, "Data").text = data
            
            # For buttons, add URL element
            if type_name == "Button":
                url_elem = SubElement(elem_list, "ContentElement")
                url_elem.set("TypeName", "Url")
                url_elem.set("IsFile", "False")
                url_elem.set("MetaDataRaw", "")
                SubElement(url_elem, "Data").text = "?optin=%%OfferId%%"
        
        # Add metadata
        meta_list = SubElement(content, "MetaDataList")
        
        # Add image metadata for OMS templates (LinkedContentCollection type)
        if include_image and self.image_key:
            image_meta = SubElement(meta_list, "MetaData")
            image_meta.set("Key", "image")
            image_meta.set("DisplayName", "Image")
            image_meta.set("MetaTypeName", "LinkedContentCollection")
            image_data = SubElement(image_meta, "Data")
            # CMS requires LinkedContentKey, LinkedDocumentKey, LinkedMarketCode, and the ID as text
            image_data.set("LinkedContentKey", self.image_key)
            image_data.set("LinkedDocumentKey", self.image_key)
            image_data.set("LinkedMarketCode", "neutral")
            image_data.text = self.image_id  # CMS content ID (e.g., "3736707")
        
        # CMS DisplayName mapping (Key -> Display Name with proper formatting)
        display_name_map = {
            "rewardType": "Reward Type",
            "taskType": "Task Type",
            "sendCondition": "Send Condition",
            "bonusProduct": "Bonus Product",
            "image": "Image",
        }
        
        for key_name, value in metadata.items():
            meta = SubElement(meta_list, "MetaData")
            meta.set("Key", key_name)
            # Use CMS display name mapping
            display_name = display_name_map.get(key_name, key_name)
            meta.set("DisplayName", display_name)
            meta.set("MetaTypeName", "List")
            SubElement(meta, "Data").text = value
        
        return content
    
    def generate_sms_xml(
        self,
        market: str,
        templates: list[TemplateContent],
        send_condition: str,
    ) -> str:
        """Generate SMS template XML for a specific market."""
        content_type = TEMPLATE_TYPES["SMS"]["content_type_name"]
        root = self._create_content_list_element(content_type, market)
        
        for template in templates:
            if template.variant not in self.variants:
                continue
            
            key = f"{content_type}.{self.offer_key}-{send_condition}-Template{template.variant}"
            
            body_text = template.body or ""
            if len(body_text) > SMS_MAX_LENGTH:
                print(f"Warning: SMS body exceeds {SMS_MAX_LENGTH} chars for {key}")
            
            content_items = [
                ("Body", "PlainText", body_text),
                ("TemplateName", "Title", f"Template{template.variant}"),
            ]
            
            metadata = {
                "rewardType": self.reward_type,
                "taskType": self.task_type,
                "sendCondition": send_condition,
            }
            if self.bonus_product:
                metadata["bonusProduct"] = self.bonus_product
            
            content = self._create_content_element(content_type, key, content_items, metadata)
            root.append(content)
        
        return self._prettify_xml(root)
    
    def generate_oms_xml(
        self,
        market: str,
        templates: list[TemplateContent],
        send_condition: str,
    ) -> str:
        """Generate OMS template XML for a specific market."""
        content_type = TEMPLATE_TYPES["OMS"]["content_type_name"]
        root = self._create_content_list_element(content_type, market)
        
        for template in templates:
            if template.variant not in self.variants:
                continue
            
            key = f"{content_type}.{self.offer_key}-{send_condition}-Template{template.variant}"
            
            content_items = [
                ("Title", "Title", template.title or ""),
                ("Body", "Text", _format_cms_text(template.body or "")),
                ("CallToAction", "Button", template.cta or "Opt-in"),
                ("CallToActionMobile", "Button", template.cta or "Opt-in"),
                ("TemplateName", "Title", f"Template{template.variant}"),
            ]
            
            metadata = {
                "rewardType": self.reward_type,
                "taskType": self.task_type,
                "sendCondition": send_condition,
            }
            if self.bonus_product:
                metadata["bonusProduct"] = self.bonus_product
            
            content = self._create_content_element(content_type, key, content_items, metadata)
            root.append(content)
        
        return self._prettify_xml(root)
    
    def generate_sms_xml_from_templates(
        self,
        market: str,
        templates: list[TemplateContent],
    ) -> str:
        """Generate SMS template XML using send_condition from each template."""
        content_type = TEMPLATE_TYPES["SMS"]["content_type_name"]
        root = self._create_content_list_element(content_type, market)
        
        for template in templates:
            if template.variant not in self.variants:
                continue
            
            send_condition = template.send_condition
            key = f"{content_type}.{self.offer_key}-{send_condition}-Template{template.variant}"
            
            body_text = template.body or ""
            if len(body_text) > SMS_MAX_LENGTH:
                print(f"Warning: SMS body exceeds {SMS_MAX_LENGTH} chars for {key}")
            
            content_items = [
                ("Body", "PlainText", body_text),
                ("TemplateName", "Title", f"Template{template.variant}"),
            ]
            
            metadata = {
                "rewardType": self.reward_type,
                "taskType": self.task_type,
                "sendCondition": send_condition,
            }
            if self.bonus_product:
                metadata["bonusProduct"] = self.bonus_product
            
            content = self._create_content_element(content_type, key, content_items, metadata)
            root.append(content)
        
        return self._prettify_xml(root)
    
    def generate_oms_xml_from_templates(
        self,
        market: str,
        templates: list[TemplateContent],
    ) -> str:
        """Generate OMS template XML using send_condition from each template."""
        content_type = TEMPLATE_TYPES["OMS"]["content_type_name"]
        root = self._create_content_list_element(content_type, market)
        
        for template in templates:
            if template.variant not in self.variants:
                continue
            
            send_condition = template.send_condition
            key = f"{content_type}.{self.offer_key}-{send_condition}-Template{template.variant}"
            
            content_items = [
                ("Title", "Title", template.title or ""),
                ("Body", "Text", _format_cms_text(template.body or "")),
                ("CallToAction", "Button", template.cta or "Opt-in"),
                ("CallToActionMobile", "Button", template.cta or "Opt-in"),
                ("TemplateName", "Title", f"Template{template.variant}"),
            ]
            
            metadata = {
                "rewardType": self.reward_type,
                "taskType": self.task_type,
                "sendCondition": send_condition,
            }
            if self.bonus_product:
                metadata["bonusProduct"] = self.bonus_product
            
            content = self._create_content_element(content_type, key, content_items, metadata, include_image=True)
            root.append(content)
        
        return self._prettify_xml(root)

    def generate_tc_xml(
        self,
        market: str,
        significant_terms: str,
        terms_and_conditions: str,
    ) -> str:
        """Generate TC template XML for a specific market."""
        content_type = TEMPLATE_TYPES["TC"]["content_type_name"]
        root = self._create_content_list_element(content_type, market)
        
        key = f"{content_type}.{self.offer_key}"
        
        content_items = [
            ("SignificantTerms", "Text", _format_cms_text(significant_terms)),
            ("TermsAndConditions", "Text", _format_cms_text(terms_and_conditions)),
        ]
        
        metadata = {
            "rewardType": self.reward_type,
            "taskType": self.task_type,
        }
        if self.bonus_product:
            metadata["bonusProduct"] = self.bonus_product
        
        content = self._create_content_element(content_type, key, content_items, metadata)
        root.append(content)
        
        return self._prettify_xml(root)
    
    def _prettify_xml(self, element: Element) -> str:
        """Convert Element to CMS-compatible XML string (minified with proper declaration)."""
        rough_string = tostring(element, encoding="unicode")
        # CMS expects: UTF-8 BOM + declaration with encoding + minified content
        return '<?xml version="1.0" encoding="utf-8"?>' + rough_string


def generate_cms_packages(
    parsed_docs: list[ParsedDocument],
    offer_key: str,
    task_type: str,
    reward_type: str,
    send_conditions: list[str],
    variants: list[str],
    bonus_product: Optional[str],
    output_dir: Path,
    image_key: Optional[str] = None,
    image_id: Optional[str] = None,
) -> dict[str, Path]:
    """
    Generate all CMS packages from parsed documents.
    
    Args:
        image_key: Image key for OMS templates - references existing image in GenericSiteMessageImageRepository
        image_id: CMS content ID for the image (from production export)
    
    Returns:
        Dictionary mapping template type to output ZIP path
    """
    generator = CmsXmlGenerator(
        offer_key=offer_key,
        task_type=task_type,
        reward_type=reward_type,
        send_conditions=send_conditions,
        variants=variants,
        bonus_product=bonus_product,
        image_key=image_key,
        image_id=image_id,
    )
    
    output_paths = {}
    
    for template_type in ["SMS", "OMS", "TC"]:
        content_type_name = TEMPLATE_TYPES[template_type]["content_type_name"]
        type_output_dir = output_dir / content_type_name
        type_output_dir.mkdir(parents=True, exist_ok=True)
        
        # Create Common folder structure
        common_dir = type_output_dir / "Common"
        common_dir.mkdir(exist_ok=True)
        
        # Write ContentTypeList.txt
        (common_dir / "ContentTypeList.txt").write_text(f"{content_type_name}\n")
        (common_dir / "DocumentTypeList.txt").write_text(f"{content_type_name}\n")
        
        # Create content type folder
        content_dir = common_dir / content_type_name
        content_dir.mkdir(exist_ok=True)
        
        # Generate description files (required for import)
        hashes = TEMPLATE_TYPES[template_type]["hashes"]
        comment = TEMPLATE_TYPES[template_type].get("comment", "")
        doc_type_id = TEMPLATE_TYPES[template_type].get("doc_type_id", 5712)
        image_link_data = TEMPLATE_TYPES[template_type].get("image_link_data", 1960)
        
        # Write ContentTypeDescription.txt and DocumentTypeDescription.txt
        # CMS uses UTF-8 with BOM (utf-8-sig) for these files
        desc_txt = _generate_description_txt(content_type_name, hashes)
        (content_dir / "ContentTypeDescription.txt").write_text(desc_txt, encoding="utf-8-sig")
        (content_dir / "DocumentTypeDescription.txt").write_text(desc_txt, encoding="utf-8-sig")
        
        # Write ContentTypeDescription.xml (with BOM)
        content_type_desc_xml = _generate_content_type_description_xml(content_type_name, comment, doc_type_id)
        (content_dir / "ContentTypeDescription.xml").write_text(content_type_desc_xml, encoding="utf-8-sig")
        
        # Write DocumentTypeDescription.xml (with BOM)
        doc_type_desc_xml = _generate_document_type_description_xml(content_type_name, comment, doc_type_id, template_type, image_link_data)
        (content_dir / "DocumentTypeDescription.xml").write_text(doc_type_desc_xml, encoding="utf-8-sig")
        
        # Copy DocumentTypeDescription.ser if available (binary .NET serialized file from CMS export)
        ser_file_name = TEMPLATE_TYPES[template_type].get("ser_file")
        if ser_file_name:
            ser_source = Path(__file__).parent / ser_file_name
            if ser_source.exists():
                import shutil
                shutil.copy(ser_source, content_dir / "DocumentTypeDescription.ser")
        
        # Generate XML for each language
        for doc in parsed_docs:
            cms_markets = LANGUAGE_MAPPING.get(doc.language_code, [doc.language_code.lower()])
            
            for market in cms_markets:
                market_dir = content_dir / market
                market_dir.mkdir(exist_ok=True)
                
                if template_type == "SMS":
                    # Process Launch SMS (NotOptedIn) and Reminder SMS (JoinedCampaign) separately
                    all_sms_templates = []
                    if doc.launch_sms:
                        all_sms_templates.extend(doc.launch_sms.templates)
                    if doc.reminder_sms:
                        all_sms_templates.extend(doc.reminder_sms.templates)
                    if all_sms_templates:
                        xml_content = generator.generate_sms_xml_from_templates(market, all_sms_templates)
                        _write_content_xml(market_dir, xml_content)
                
                elif template_type == "OMS":
                    # Process Launch OMS (NotOptedIn), Reminder OMS (JoinedCampaign), and Reward OMS (ClaimedReward)
                    all_oms_templates = []
                    if doc.launch_oms:
                        all_oms_templates.extend(doc.launch_oms.templates)
                    if doc.reminder_oms:
                        all_oms_templates.extend(doc.reminder_oms.templates)
                    if doc.reward_oms:
                        all_oms_templates.extend(doc.reward_oms.templates)
                    if all_oms_templates:
                        xml_content = generator.generate_oms_xml_from_templates(market, all_oms_templates)
                        _write_content_xml(market_dir, xml_content)
                
                elif template_type == "TC":
                    if doc.tc:
                        xml_content = generator.generate_tc_xml(
                            market,
                            doc.tc.significant_terms or "",
                            doc.tc.terms_and_conditions or "",
                        )
                        _write_content_xml(market_dir, xml_content)
        
        output_paths[template_type] = type_output_dir
    
    return output_paths


def _write_content_xml(market_dir: Path, xml_content: str):
    """Write ContentList.xml and DocumentList.xml in market directory."""
    content_file = market_dir / "ContentList.xml"
    
    if content_file.exists():
        # Merge with existing content (simplified - just overwrite for now)
        pass
    
    # CMS requires UTF-8 BOM encoding (utf-8-sig)
    content_file.write_text(xml_content, encoding="utf-8-sig")
    
    # Generate DocumentList.xml with correct schema (different element names)
    doc_xml = _convert_content_to_document_xml(xml_content)
    doc_file = market_dir / "DocumentList.xml"
    doc_file.write_text(doc_xml, encoding="utf-8-sig")


def _convert_content_to_document_xml(content_xml: str) -> str:
    """Convert ContentList.xml format to DocumentList.xml format.
    
    CMS uses different element/attribute names for DocumentList:
    - ContentList -> DocumentList
    - ContentTypeName -> DocumentTypeName  
    - Content -> Document
    - ContentItemList -> ComponentList
    - ContentItem -> Component
    - ContentElementList -> AttributeList
    - ContentElement -> Attribute
    - ContentMarketList -> DocumentMarketList
    - ContentProfileList -> DocumentProfileList
    """
    # Replace element names
    doc_xml = content_xml
    
    # Root element and attributes
    doc_xml = doc_xml.replace('ContentList ContentTypeName=', 'DocumentList DocumentTypeName=')
    doc_xml = doc_xml.replace('ContentTypeHash=', 'DocumentTypeHash=')
    doc_xml = doc_xml.replace('ContentTypeHeadHash=', 'DocumentTypeHeadHash=')
    doc_xml = doc_xml.replace('ContentTypeRulesHash=', 'DocumentTypeRulesHash=')
    doc_xml = doc_xml.replace('ContentTypeMetasHash=', 'DocumentTypeMetasHash=')
    doc_xml = doc_xml.replace('ContentTypeHeadHashV2=', 'DocumentTypeHeadHashV2=')
    doc_xml = doc_xml.replace('ContentTypeMerchant=', 'DocumentTypeMerchant=')
    doc_xml = doc_xml.replace('ContentTypeBrand=', 'DocumentTypeBrand=')
    doc_xml = doc_xml.replace('ContentTypeProduct=', 'DocumentTypeProduct=')
    doc_xml = doc_xml.replace('</ContentList>', '</DocumentList>')
    
    # Content -> Document
    doc_xml = doc_xml.replace('<Content ', '<Document ')
    doc_xml = doc_xml.replace('</Content>', '</Document>')
    
    # ContentItemList -> ComponentList
    doc_xml = doc_xml.replace('<ContentItemList>', '<ComponentList>')
    doc_xml = doc_xml.replace('</ContentItemList>', '</ComponentList>')
    
    # ContentItem -> Component (remove ContentRuleName and ContentRuleId attributes)
    import re
    # Match ContentItem and remove ContentRuleName and ContentRuleId
    doc_xml = re.sub(
        r'<ContentItem ([^>]*?)ContentRuleName="[^"]*" ([^>]*?)ContentRuleId="[^"]*"([^>]*)>',
        r'<Component \1\2\3>',
        doc_xml
    )
    doc_xml = doc_xml.replace('</ContentItem>', '</Component>')
    
    # ContentElementList -> AttributeList
    doc_xml = doc_xml.replace('<ContentElementList>', '<AttributeList>')
    doc_xml = doc_xml.replace('</ContentElementList>', '</AttributeList>')
    
    # ContentElement -> Attribute
    doc_xml = doc_xml.replace('<ContentElement ', '<Attribute ')
    doc_xml = doc_xml.replace('</ContentElement>', '</Attribute>')
    
    # ContentMarketList -> DocumentMarketList
    doc_xml = doc_xml.replace('<ContentMarketList', '<DocumentMarketList')
    doc_xml = doc_xml.replace('</ContentMarketList>', '</DocumentMarketList>')
    
    # ContentProfileList -> DocumentProfileList
    doc_xml = doc_xml.replace('<ContentProfileList', '<DocumentProfileList')
    doc_xml = doc_xml.replace('</ContentProfileList>', '</DocumentProfileList>')
    
    return doc_xml
