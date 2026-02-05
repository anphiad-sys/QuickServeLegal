"""
QuickServe Legal - OCR Document Processor

Uses Claude Vision API to extract structured data from legal documents.
This is a SHARED feature used by:
- QSL Members: Auto-complete upload form fields
- PNSA Branches: Extract all party details from scanned documents
"""

import base64
import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List
import json
import logging

from src.config import settings

logger = logging.getLogger(__name__)


@dataclass
class AttorneyInfo:
    """Extracted attorney information from a legal document."""
    name: Optional[str] = None
    firm: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None


@dataclass
class DocumentExtraction:
    """Structured data extracted from a legal document."""
    plaintiff: Optional[str] = None
    defendant: Optional[str] = None
    case_number: Optional[str] = None
    court_name: Optional[str] = None
    pleading_type: Optional[str] = None
    serving_attorney: AttorneyInfo = field(default_factory=AttorneyInfo)
    recipient_attorney: AttorneyInfo = field(default_factory=AttorneyInfo)
    confidence_score: float = 0.0
    raw_text: Optional[str] = None


# South African court document extraction prompt
SA_LEGAL_EXTRACTION_PROMPT = """Analyze this South African legal document and extract the following information in JSON format.

**IMPORTANT INSTRUCTIONS FOR FINDING ATTORNEY DETAILS:**
- Attorney contact details are ALWAYS found at the END of the document
- If there is a filing sheet (stamped page with "REGISTRAR" at top), attorney details are at the END of the filing sheet
- Look for blocks of text containing firm names, addresses, phone numbers, fax numbers, email addresses, and reference numbers
- The SERVING attorney (who prepared/sent the document) typically appears with their letterhead OR in a signature block
- The RECEIVING attorney (who the document is addressed to) is often marked with "TO:", "SERVICE:", "Served on:", or "c/o"
- Attorney blocks typically contain: Firm name (often ending in "INC", "INC.", "INCORPORATED", "ATTORNEYS"), physical address, Tel/Phone, Fax, Email, Ref/Reference

**Extract the following:**

1. **Case Details (usually on FIRST page):**
   - case_number: The case/matter number (e.g., "12345/2026", "A123/2026", "86332/2018")
   - court_name: The court name (e.g., "High Court of South Africa, Gauteng Division, Pretoria")
   - pleading_type: The type of document (e.g., "Summons", "Notice of Motion", "Plea", "Declaration", "Notice of Intention to Defend")

2. **Parties (usually on FIRST page):**
   - plaintiff: The plaintiff/applicant name(s)
   - defendant: The defendant/respondent name(s)

3. **Serving Attorney (found at END of document - the attorney who prepared/sent this document):**
   - serving_attorney_name: Full name of the attorney (individual, not firm)
   - serving_attorney_firm: Law firm name (e.g., "VAN BREDA & HERBST INC.", "SMITH ATTORNEYS")
   - serving_attorney_email: Email address (often ends in .co.za)
   - serving_attorney_phone: Phone/Tel number (format: +27..., 012..., (012)...)
   - serving_attorney_address: Physical address (street, suburb, city)

4. **Recipient Attorney (found at END of document - marked "TO:" or "SERVICE:"):**
   - recipient_attorney_name: Full name of the attorney (individual, not firm)
   - recipient_attorney_firm: Law firm name
   - recipient_attorney_email: Email address
   - recipient_attorney_phone: Phone/Tel number
   - recipient_attorney_address: Physical address

Return ONLY a valid JSON object with this structure:
{
    "case_number": "string or null",
    "court_name": "string or null",
    "pleading_type": "string or null",
    "plaintiff": "string or null",
    "defendant": "string or null",
    "serving_attorney_name": "string or null",
    "serving_attorney_firm": "string or null",
    "serving_attorney_email": "string or null",
    "serving_attorney_phone": "string or null",
    "serving_attorney_address": "string or null",
    "recipient_attorney_name": "string or null",
    "recipient_attorney_firm": "string or null",
    "recipient_attorney_email": "string or null",
    "recipient_attorney_phone": "string or null",
    "recipient_attorney_address": "string or null",
    "confidence_score": 0.0 to 1.0
}

**Additional Notes:**
- South African case numbers follow patterns like "12345/2026", "A123/2026", or "86332/2018"
- Email addresses often end in .co.za or .com
- Phone numbers start with +27, 0XX, or (0XX) - e.g., "012 848 1082", "(012) 361 0951"
- Look for "Ref:" or "Reference:" lines near attorney details
- If you see "Per:" followed by a name, that's likely the individual attorney
- Set confidence_score based on how clearly the information was found (1.0 = very clear, 0.5 = partial, 0.0 = not found)
"""


async def convert_pdf_to_images(pdf_path: Path, max_pages: int = 3) -> List[bytes]:
    """
    Convert PDF pages to images for OCR processing.

    Captures BOTH first pages (for case details) AND last pages (for attorney details).

    Args:
        pdf_path: Path to the PDF file
        max_pages: Maximum number of pages from each end to convert

    Returns:
        List of PNG image bytes
    """
    try:
        from pdf2image import convert_from_path, pdfinfo_from_path
        from PIL import Image

        # Get total page count
        try:
            pdf_info = pdfinfo_from_path(pdf_path)
            total_pages = pdf_info.get('Pages', 1)
        except Exception:
            total_pages = 1

        logger.info(f"PDF has {total_pages} pages")

        images = []

        # Get first pages (for case details, parties)
        first_pages_count = min(max_pages, total_pages)
        first_images = convert_from_path(
            pdf_path,
            first_page=1,
            last_page=first_pages_count,
            dpi=150,
        )
        images.extend(first_images)
        logger.info(f"Extracted first {len(first_images)} pages")

        # Get last pages (for attorney details) - only if document is longer
        if total_pages > max_pages:
            # Calculate which pages to get from the end
            last_start = max(total_pages - max_pages + 1, max_pages + 1)
            last_images = convert_from_path(
                pdf_path,
                first_page=last_start,
                last_page=total_pages,
                dpi=150,
            )
            images.extend(last_images)
            logger.info(f"Extracted last {len(last_images)} pages (pages {last_start}-{total_pages})")

        image_bytes_list = []
        for img in images:
            # Convert to RGB if necessary
            if img.mode != 'RGB':
                img = img.convert('RGB')

            # Resize if too large (max 1568px on longest side per Claude API)
            max_size = 1568
            if max(img.size) > max_size:
                ratio = max_size / max(img.size)
                new_size = (int(img.width * ratio), int(img.height * ratio))
                img = img.resize(new_size, Image.Resampling.LANCZOS)

            # Convert to bytes
            buffer = io.BytesIO()
            img.save(buffer, format='PNG', optimize=True)
            image_bytes_list.append(buffer.getvalue())

        return image_bytes_list

    except ImportError as e:
        logger.error(f"pdf2image or Pillow not installed: {e}")
        raise RuntimeError("PDF conversion dependencies not installed. Run: pip install pdf2image Pillow")
    except Exception as e:
        logger.error(f"Error converting PDF to images: {e}")
        raise


async def extract_with_claude_vision(image_bytes_list: List[bytes]) -> dict:
    """
    Send images to Claude Vision API and extract document data.

    Args:
        image_bytes_list: List of PNG image bytes

    Returns:
        Extracted data as dictionary
    """
    try:
        import anthropic

        if not settings.ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY not configured")

        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

        # Build content with images
        content = []
        for img_bytes in image_bytes_list:
            img_b64 = base64.standard_b64encode(img_bytes).decode('utf-8')
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": img_b64,
                }
            })

        # Add the extraction prompt
        content.append({
            "type": "text",
            "text": SA_LEGAL_EXTRACTION_PROMPT
        })

        # Call Claude Vision
        message = client.messages.create(
            model="claude-sonnet-4-20250514",  # Use Sonnet for cost-effective vision
            max_tokens=2000,
            messages=[
                {
                    "role": "user",
                    "content": content
                }
            ]
        )

        # Parse the response
        response_text = message.content[0].text

        # Extract JSON from response (handle potential markdown code blocks)
        if "```json" in response_text:
            json_str = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            json_str = response_text.split("```")[1].split("```")[0].strip()
        else:
            json_str = response_text.strip()

        return json.loads(json_str)

    except ImportError:
        logger.error("anthropic package not installed")
        raise RuntimeError("Anthropic package not installed. Run: pip install anthropic")
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Claude response as JSON: {e}")
        return {}
    except Exception as e:
        logger.error(f"Error calling Claude Vision API: {e}")
        raise


def parse_extraction_result(data: dict) -> DocumentExtraction:
    """
    Parse raw extraction data into structured DocumentExtraction.

    Args:
        data: Raw dictionary from Claude Vision

    Returns:
        Structured DocumentExtraction object
    """
    serving_attorney = AttorneyInfo(
        name=data.get("serving_attorney_name"),
        firm=data.get("serving_attorney_firm"),
        email=data.get("serving_attorney_email"),
        phone=data.get("serving_attorney_phone"),
        address=data.get("serving_attorney_address"),
    )

    recipient_attorney = AttorneyInfo(
        name=data.get("recipient_attorney_name"),
        firm=data.get("recipient_attorney_firm"),
        email=data.get("recipient_attorney_email"),
        phone=data.get("recipient_attorney_phone"),
        address=data.get("recipient_attorney_address"),
    )

    return DocumentExtraction(
        plaintiff=data.get("plaintiff"),
        defendant=data.get("defendant"),
        case_number=data.get("case_number"),
        court_name=data.get("court_name"),
        pleading_type=data.get("pleading_type"),
        serving_attorney=serving_attorney,
        recipient_attorney=recipient_attorney,
        confidence_score=data.get("confidence_score", 0.0),
    )


async def extract_document_data(pdf_path: Path) -> DocumentExtraction:
    """
    Extract structured data from a legal document PDF using Claude Vision.

    This is the main entry point for full document extraction.

    Args:
        pdf_path: Path to the PDF file

    Returns:
        DocumentExtraction with all extracted fields
    """
    if not settings.OCR_ENABLED:
        logger.info("OCR is disabled in settings")
        return DocumentExtraction()

    try:
        # Convert PDF to images
        max_pages = getattr(settings, 'OCR_MAX_PAGES', 3)
        image_bytes_list = await convert_pdf_to_images(pdf_path, max_pages=max_pages)

        if not image_bytes_list:
            logger.warning("No images extracted from PDF")
            return DocumentExtraction()

        # Extract data using Claude Vision
        raw_data = await extract_with_claude_vision(image_bytes_list)

        # Parse into structured format
        extraction = parse_extraction_result(raw_data)

        logger.info(f"Document extraction completed with confidence: {extraction.confidence_score}")
        return extraction

    except Exception as e:
        logger.error(f"Document extraction failed: {e}")
        return DocumentExtraction()


async def extract_for_upload_form(pdf_path: Path) -> dict:
    """
    Simplified extraction for member upload - returns suggested form values.

    This is a convenience function that extracts only the fields needed
    for the upload form auto-complete feature.

    Args:
        pdf_path: Path to the PDF file

    Returns:
        Dictionary with suggested form values:
        {
            "recipient_email": str or None,
            "recipient_name": str or None,
            "matter_reference": str or None,
            "description": str or None,
            "confidence": float
        }
    """
    extraction = await extract_document_data(pdf_path)

    # Build matter reference from case number and court
    matter_reference = None
    if extraction.case_number:
        matter_reference = extraction.case_number
        if extraction.court_name:
            # Shorten court name for reference
            court_short = extraction.court_name.replace("High Court of South Africa, ", "")
            matter_reference = f"{extraction.case_number} ({court_short})"

    # Build description from pleading type and parties
    description_parts = []
    if extraction.pleading_type:
        description_parts.append(extraction.pleading_type)
    if extraction.plaintiff and extraction.defendant:
        description_parts.append(f"{extraction.plaintiff} v {extraction.defendant}")
    elif extraction.plaintiff:
        description_parts.append(f"Applicant: {extraction.plaintiff}")
    elif extraction.defendant:
        description_parts.append(f"Respondent: {extraction.defendant}")

    description = " - ".join(description_parts) if description_parts else None

    # Get recipient info
    recipient_email = extraction.recipient_attorney.email
    recipient_name = extraction.recipient_attorney.name
    if not recipient_name and extraction.recipient_attorney.firm:
        recipient_name = extraction.recipient_attorney.firm

    return {
        "recipient_email": recipient_email,
        "recipient_name": recipient_name,
        "matter_reference": matter_reference,
        "description": description,
        "confidence": extraction.confidence_score,
    }


async def extract_for_pnsa_service(pdf_path: Path) -> dict:
    """
    Full extraction for PNSA walk-in service - returns all extracted data.

    This provides all the extracted information needed for the PNSA
    branch operator to review and confirm before serving.

    Args:
        pdf_path: Path to the PDF file

    Returns:
        Dictionary with all extracted fields for PNSA workflow
    """
    extraction = await extract_document_data(pdf_path)

    return {
        # Case details
        "case_number": extraction.case_number,
        "court_name": extraction.court_name,
        "pleading_type": extraction.pleading_type,
        "plaintiff": extraction.plaintiff,
        "defendant": extraction.defendant,

        # Serving attorney (who brought the document)
        "serving_attorney_name": extraction.serving_attorney.name,
        "serving_attorney_firm": extraction.serving_attorney.firm,
        "serving_attorney_email": extraction.serving_attorney.email,
        "serving_attorney_phone": extraction.serving_attorney.phone,
        "serving_attorney_address": extraction.serving_attorney.address,

        # Recipient attorney (QSL member to receive document)
        "recipient_attorney_name": extraction.recipient_attorney.name,
        "recipient_attorney_firm": extraction.recipient_attorney.firm,
        "recipient_attorney_email": extraction.recipient_attorney.email,
        "recipient_attorney_phone": extraction.recipient_attorney.phone,
        "recipient_attorney_address": extraction.recipient_attorney.address,

        # Confidence
        "confidence": extraction.confidence_score,
    }
