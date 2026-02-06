"""
QuickServe Legal - PDF Generation

Generates:
1. Proof of Service PDF - Court-ready document proving service
2. Stamped PDF - Original document with receipt verification stamp
3. Wet-Ink Placeholder Page - Signature block for AES workflow
4. Court Filing Certificate - Full certificate for court filing
"""

import io
from datetime import datetime
from pathlib import Path
from src.timestamps import format_sast
from typing import Optional, TYPE_CHECKING
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
from reportlab.pdfgen import canvas
from pypdf import PdfReader, PdfWriter

from src.config import settings
from src.models.document import Document

if TYPE_CHECKING:
    from src.models.signature import Signature
    from src.models.certificate import Certificate


# =============================================================================
# PROOF OF SERVICE PDF
# =============================================================================

def generate_proof_of_service(
    document: Document,
    signature: Optional["Signature"] = None,
    certificate: Optional["Certificate"] = None,
) -> bytes:
    """
    Generate a Proof of Service PDF document.

    Args:
        document: The Document model instance
        signature: Optional Signature model (for AES info)
        certificate: Optional Certificate model (for AES info)

    Returns the PDF as bytes.
    """
    buffer = io.BytesIO()

    # Create the PDF document
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2*cm,
    )

    # Styles
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name='QSLTitle',
        parent=styles['Title'],
        fontSize=18,
        spaceAfter=12,
    ))
    styles.add(ParagraphStyle(
        name='QSLHeading',
        parent=styles['Heading2'],
        fontSize=12,
        spaceBefore=12,
        spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        name='QSLBody',
        parent=styles['BodyText'],
        fontSize=10,
        spaceBefore=3,
        spaceAfter=3,
    ))
    styles.add(ParagraphStyle(
        name='QSLLegal',
        parent=styles['BodyText'],
        fontSize=9,
        textColor=colors.grey,
        spaceBefore=6,
    ))

    # Build content
    story = []

    # Header
    story.append(Paragraph("PROOF OF SERVICE", styles['QSLTitle']))
    story.append(Paragraph("Electronic Service via QuickServe Legal", styles['QSLHeading']))
    story.append(Spacer(1, 0.5*cm))

    # Reference number
    story.append(Paragraph(
        f"<b>Reference Number:</b> QSL-{document.id:06d}",
        styles['QSLBody']
    ))
    story.append(Spacer(1, 0.5*cm))

    # Document Details Section
    story.append(Paragraph("1. DOCUMENT DETAILS", styles['QSLHeading']))

    doc_data = [
        ["Document Name:", document.original_filename],
        ["File Size:", f"{document.file_size:,} bytes"],
        ["Matter Reference:", document.matter_reference or "Not specified"],
        ["Description:", document.description or "Not specified"],
    ]

    doc_table = Table(doc_data, colWidths=[4*cm, 12*cm])
    doc_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(doc_table)
    story.append(Spacer(1, 0.5*cm))

    # Sender Details Section
    story.append(Paragraph("2. SENDER (SERVING PARTY)", styles['QSLHeading']))

    sender_data = [
        ["Name:", document.sender_name],
        ["Email:", document.sender_email],
        ["Firm:", "As per sender's registration details"],
    ]

    sender_table = Table(sender_data, colWidths=[4*cm, 12*cm])
    sender_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(sender_table)
    story.append(Spacer(1, 0.5*cm))

    # Recipient Details Section
    story.append(Paragraph("3. RECIPIENT (SERVED PARTY)", styles['QSLHeading']))

    recipient_data = [
        ["Name:", document.recipient_name or "Not specified"],
        ["Email:", document.recipient_email],
    ]

    recipient_table = Table(recipient_data, colWidths=[4*cm, 12*cm])
    recipient_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(recipient_table)
    story.append(Spacer(1, 0.5*cm))

    # Service Details Section
    story.append(Paragraph("4. SERVICE DETAILS", styles['QSLHeading']))

    # Format timestamps for South African timezone display
    # Per ECTA Section 23: Document is "received" when it enters the recipient's
    # information system and is capable of being retrieved (i.e., when email is sent)
    if document.served_at:
        served_time = document.served_at.strftime("%d %B %Y at %H:%M:%S SAST")
    elif document.notified_at:
        served_time = document.notified_at.strftime("%d %B %Y at %H:%M:%S SAST")
    else:
        served_time = document.created_at.strftime("%d %B %Y at %H:%M:%S SAST")

    # Determine service status based on email delivery tracking
    if document.is_email_delivered:
        service_status = "COMPLETE - Email delivered to recipient's mail server"
    elif document.email_status == "bounced":
        service_status = "FAILED - Email bounced (see delivery details below)"
    elif document.email_status == "sent":
        service_status = "PENDING - Email sent, awaiting delivery confirmation"
    else:
        service_status = "COMPLETE - Notification sent to recipient's email"

    service_data = [
        ["Date/Time of Service:", served_time],
        ["Method:", "Electronic service via QuickServe Legal platform"],
        ["Recipient Email:", document.recipient_email],
        ["Service Status:", service_status],
    ]

    service_table = Table(service_data, colWidths=[4*cm, 12*cm])
    service_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(service_table)
    story.append(Spacer(1, 0.5*cm))

    # Email Delivery Tracking Section (if available)
    if document.email_message_id or document.email_delivered_at:
        story.append(Paragraph("5. EMAIL DELIVERY CONFIRMATION", styles['QSLHeading']))

        # Map email status to user-friendly description
        status_descriptions = {
            "pending": "Pending - Email queued for delivery",
            "sent": "Sent - Email accepted by mail service",
            "delivered": "DELIVERED - Email accepted by recipient's mail server",
            "opened": "DELIVERED & OPENED - Recipient opened the email",
            "clicked": "DELIVERED & OPENED - Recipient clicked download link",
            "bounced": "BOUNCED - Email rejected by recipient's mail server",
            "failed": "FAILED - Permanent delivery failure",
        }
        email_status_display = status_descriptions.get(
            document.email_status,
            document.email_status.upper() if document.email_status else "Unknown"
        )

        email_data = [
            ["Tracking ID:", document.email_message_id or "N/A"],
            ["Delivery Status:", email_status_display],
        ]

        # Add delivery timestamp if available
        if document.email_delivered_at:
            email_data.append([
                "Delivered At:",
                document.email_delivered_at.strftime("%d %B %Y at %H:%M:%S SAST")
            ])

        # Add opened timestamp if available
        if document.email_opened_at:
            email_data.append([
                "Opened At:",
                document.email_opened_at.strftime("%d %B %Y at %H:%M:%S SAST")
            ])

        # Add bounce reason if applicable
        if document.email_status == "bounced" and document.email_bounce_reason:
            email_data.append(["Bounce Reason:", document.email_bounce_reason])

        email_table = Table(email_data, colWidths=[4*cm, 12*cm])

        # Highlight delivered status in green, bounced in red
        table_style = [
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]

        if document.is_email_delivered:
            table_style.append(('BACKGROUND', (0, 1), (-1, 1), colors.Color(0.9, 1, 0.9)))
        elif document.email_status == "bounced":
            table_style.append(('BACKGROUND', (0, 1), (-1, 1), colors.Color(1, 0.9, 0.9)))

        email_table.setStyle(TableStyle(table_style))
        story.append(email_table)

        # Add ECTA explanation
        if document.is_email_delivered:
            story.append(Spacer(1, 0.3*cm))
            ecta_note = """
            <i>Per Section 23 of ECTA: The above delivery confirmation proves that the data message
            (email with attached document) entered the recipient's designated information system
            (email server) and became capable of being retrieved. Service is therefore complete.</i>
            """
            story.append(Paragraph(ecta_note.strip(), styles['QSLLegal']))

        story.append(Spacer(1, 0.5*cm))

    # Track section number based on whether email tracking section was added
    next_section = 6 if (document.email_message_id or document.email_delivered_at) else 5

    # AES Signature Section (if signed)
    if document.is_signed and signature and certificate:
        story.append(Paragraph(f"{next_section}. ADVANCED ELECTRONIC SIGNATURE (AES)", styles['QSLHeading']))

        aes_data = [
            ["Signing Status:", "SIGNED with Advanced Electronic Signature"],
            ["Signed By:", certificate.common_name if certificate else document.sender_name],
            ["Certificate Serial:", certificate.certificate_serial if certificate else "N/A"],
            ["Certificate Issuer:", certificate.issuer if certificate else "N/A"],
            ["Signed At:", document.signed_at.strftime("%d %B %Y at %H:%M:%S SAST") if document.signed_at else "N/A"],
            ["Document Hash (SHA-256):", document.document_hash[:32] + "..." if document.document_hash else "N/A"],
            ["LAWTrust Reference:", signature.lawtrust_reference if signature else "N/A"],
        ]

        aes_table = Table(aes_data, colWidths=[4*cm, 12*cm])
        aes_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.9, 1, 0.9)),  # Light green for first row
        ]))
        story.append(aes_table)
        story.append(Spacer(1, 0.5*cm))

        next_section += 1

    story.append(Paragraph(f"{next_section}. VERIFICATION", styles['QSLHeading']))

    verification_text = """
    I hereby certify that the above-mentioned document was served electronically via the
    QuickServe Legal platform. The recipient was notified by email at the address stated above,
    and the document was made available for download via a secure, time-limited link.

    In accordance with Section 23 of the Electronic Communications and Transactions Act 25 of 2002
    (ECTA), the document is deemed to have been received when the data message entered the
    recipient's designated information system (email) and became capable of being retrieved.
    """

    if document.is_signed:
        verification_text += """

    The document was digitally signed using an Advanced Electronic Signature (AES) in accordance
    with Section 13 of the Electronic Communications and Transactions Act 25 of 2002 (ECTA).
        """

    story.append(Paragraph(verification_text.strip(), styles['QSLBody']))
    story.append(Spacer(1, 1*cm))

    # Legal Notice
    story.append(Paragraph("LEGAL NOTICE", styles['QSLHeading']))

    legal_text = """
    This Proof of Service is generated by QuickServe Legal (Pty) Ltd in accordance with the
    Electronic Communications and Transactions Act 25 of 2002 (ECTA) and Rule 4A of the Uniform
    Rules of Court pertaining to electronic service of subsequent documents.

    The timestamps recorded in this document are based on South African Standard Time (SAST, UTC+2)
    and are derived from the QuickServe Legal server clock, which is synchronised with reliable
    time sources.

    This document serves as prima facie proof of electronic service and may be submitted to Court
    as evidence of service.
    """

    story.append(Paragraph(legal_text.strip(), styles['QSLLegal']))
    story.append(Spacer(1, 1*cm))

    # Footer with generation timestamp
    gen_time = format_sast(datetime.utcnow())
    story.append(Paragraph(
        f"<i>This Proof of Service was generated on {gen_time}</i>",
        styles['QSLLegal']
    ))
    story.append(Paragraph(
        f"<i>QuickServe Legal Reference: QSL-{document.id:06d}</i>",
        styles['QSLLegal']
    ))

    # Build PDF
    doc.build(story)

    buffer.seek(0)
    return buffer.getvalue()


# =============================================================================
# STAMPED PDF (Original document with receipt confirmation)
# =============================================================================

def create_stamp_overlay(document: Document, page_width: float, page_height: float) -> bytes:
    """
    Create a transparent overlay with the receipt stamp.

    Returns PDF bytes of the overlay.
    """
    buffer = io.BytesIO()

    c = canvas.Canvas(buffer, pagesize=(page_width, page_height))

    # Stamp dimensions and position (bottom right corner)
    stamp_width = 200
    stamp_height = 80
    margin = 20
    x = page_width - stamp_width - margin
    y = margin

    # Draw stamp background (semi-transparent green)
    c.saveState()

    # Outer border
    c.setStrokeColor(colors.Color(0.05, 0.5, 0.05, alpha=0.9))
    c.setLineWidth(2)
    c.roundRect(x, y, stamp_width, stamp_height, 5, stroke=1, fill=0)

    # Inner fill (light green, semi-transparent)
    c.setFillColor(colors.Color(0.9, 1, 0.9, alpha=0.95))
    c.roundRect(x + 2, y + 2, stamp_width - 4, stamp_height - 4, 4, stroke=0, fill=1)

    # "SERVED" header (per ECTA Section 23)
    c.setFillColor(colors.Color(0.05, 0.5, 0.05))
    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(x + stamp_width/2, y + stamp_height - 18, "SERVED")

    # Recipient email
    c.setFont("Helvetica", 8)
    c.setFillColor(colors.Color(0.1, 0.1, 0.1))
    c.drawCentredString(x + stamp_width/2, y + stamp_height - 32, f"On: {document.recipient_email}")

    # Date and time (use served_at per ECTA Section 23)
    if document.served_at:
        date_str = document.served_at.strftime("%d %b %Y")
        time_str = document.served_at.strftime("%H:%M SAST")
    elif document.notified_at:
        date_str = document.notified_at.strftime("%d %b %Y")
        time_str = document.notified_at.strftime("%H:%M SAST")
    else:
        date_str = "Pending"
        time_str = ""

    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(x + stamp_width/2, y + stamp_height - 46, f"Date: {date_str}")
    if time_str:
        c.drawCentredString(x + stamp_width/2, y + stamp_height - 58, f"Time: {time_str}")

    # QuickServe Legal footer
    c.setFont("Helvetica-Oblique", 7)
    c.setFillColor(colors.Color(0.3, 0.3, 0.3))
    c.drawCentredString(x + stamp_width/2, y + 8, "via QuickServe Legal")

    c.restoreState()
    c.save()

    buffer.seek(0)
    return buffer.getvalue()


def generate_stamped_pdf(document: Document, original_pdf_path: Path) -> bytes:
    """
    Generate a stamped version of the original PDF with receipt confirmation.

    Args:
        document: The Document model instance
        original_pdf_path: Path to the original PDF file

    Returns:
        The stamped PDF as bytes
    """
    # Read the original PDF
    original_reader = PdfReader(str(original_pdf_path))

    # Create output PDF
    output = PdfWriter()

    # Process each page
    for page_num, page in enumerate(original_reader.pages):
        # Get page dimensions
        media_box = page.mediabox
        page_width = float(media_box.width)
        page_height = float(media_box.height)

        # Create stamp overlay (only on first page)
        if page_num == 0:
            stamp_bytes = create_stamp_overlay(document, page_width, page_height)
            stamp_reader = PdfReader(io.BytesIO(stamp_bytes))
            stamp_page = stamp_reader.pages[0]

            # Merge stamp onto the page
            page.merge_page(stamp_page)

        output.add_page(page)

    # Write to buffer
    buffer = io.BytesIO()
    output.write(buffer)
    buffer.seek(0)

    return buffer.getvalue()


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_proof_of_service_filename(document: Document) -> str:
    """Generate filename for Proof of Service PDF."""
    return f"ProofOfService_QSL-{document.id:06d}.pdf"


def get_stamped_pdf_filename(document: Document) -> str:
    """Generate filename for stamped PDF."""
    base_name = Path(document.original_filename).stem
    return f"{base_name}_RECEIVED.pdf"


# =============================================================================
# WET-INK PLACEHOLDER PAGE
# =============================================================================

def generate_wet_ink_placeholder_page() -> bytes:
    """
    Generate a single-page PDF with a wet-ink signature placeholder block.

    This page is appended to documents before AES signing to provide
    a visual signature block that complies with traditional expectations
    while the actual signature is applied digitally.

    Returns:
        PDF bytes of the placeholder page
    """
    buffer = io.BytesIO()

    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    # Page header
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(width/2, height - 3*cm, "SIGNATURE PAGE")

    c.setFont("Helvetica", 10)
    c.drawCentredString(width/2, height - 3.8*cm,
                       "Advanced Electronic Signature (AES) Certification")

    # Signature box
    box_width = 14*cm
    box_height = 6*cm
    box_x = (width - box_width) / 2
    box_y = height - 12*cm

    # Draw signature box border
    c.setStrokeColor(colors.black)
    c.setLineWidth(1)
    c.rect(box_x, box_y, box_width, box_height)

    # Signature line
    line_y = box_y + 2*cm
    line_x1 = box_x + 2*cm
    line_x2 = box_x + box_width - 2*cm
    c.line(line_x1, line_y, line_x2, line_y)

    # Labels
    c.setFont("Helvetica", 9)
    c.drawString(line_x1, line_y - 0.5*cm, "Signature:")
    c.drawString(line_x1, box_y + 4*cm, "Signed by:")
    c.drawString(line_x1, box_y + 3.3*cm, "Date:")

    # "DIGITALLY SIGNED" watermark text
    c.saveState()
    c.setFillColor(colors.Color(0.8, 0.8, 0.8))
    c.setFont("Helvetica-Bold", 24)
    c.translate(width/2, box_y + box_height/2)
    c.rotate(30)
    c.drawCentredString(0, 0, "DIGITALLY SIGNED")
    c.restoreState()

    # Legal text below signature box
    c.setFont("Helvetica", 8)
    legal_text = [
        "This document has been signed with an Advanced Electronic Signature (AES)",
        "in accordance with Section 13 of the Electronic Communications and Transactions",
        "Act 25 of 2002 (ECTA). The digital signature provides the same legal effect",
        "as a manuscript signature on a paper document.",
        "",
        "The AES ensures the integrity of this document and confirms the identity of",
        "the signatory. Any alteration to this document after signing will invalidate",
        "the digital signature.",
    ]

    text_y = box_y - 1*cm
    for line in legal_text:
        c.drawCentredString(width/2, text_y, line)
        text_y -= 0.4*cm

    # Footer
    c.setFont("Helvetica-Oblique", 8)
    c.setFillColor(colors.grey)
    c.drawCentredString(width/2, 2*cm, "Generated by QuickServe Legal - Electronic Service Platform")

    c.save()
    buffer.seek(0)
    return buffer.getvalue()


def append_wet_ink_placeholder(original_pdf_path: Path, output_path: Path) -> Path:
    """
    Append a wet-ink placeholder page to a PDF document.

    Args:
        original_pdf_path: Path to the original PDF
        output_path: Path where the combined PDF will be saved

    Returns:
        Path to the output file
    """
    # Read original PDF
    original_reader = PdfReader(str(original_pdf_path))

    # Create placeholder page
    placeholder_bytes = generate_wet_ink_placeholder_page()
    placeholder_reader = PdfReader(io.BytesIO(placeholder_bytes))

    # Combine PDFs
    output = PdfWriter()

    # Add all original pages
    for page in original_reader.pages:
        output.add_page(page)

    # Add placeholder page
    output.add_page(placeholder_reader.pages[0])

    # Write output
    with open(output_path, "wb") as f:
        output.write(f)

    return output_path


# =============================================================================
# COURT FILING CERTIFICATE
# =============================================================================

def generate_court_filing_certificate(
    document: Document,
    signature: "Signature",
    certificate: "Certificate",
) -> bytes:
    """
    Generate a Court Filing Certificate PDF.

    This comprehensive certificate provides all details needed for
    court filing, including document particulars, AES signature details,
    service particulars, and certification statements.

    Args:
        document: The Document model instance
        signature: The Signature model instance
        certificate: The Certificate model instance

    Returns:
        PDF bytes of the Court Filing Certificate
    """
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2*cm,
    )

    # Styles
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name='CFCTitle',
        parent=styles['Title'],
        fontSize=16,
        spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        name='CFCSubtitle',
        parent=styles['Normal'],
        fontSize=12,
        alignment=1,  # Center
        spaceAfter=12,
    ))
    styles.add(ParagraphStyle(
        name='CFCHeading',
        parent=styles['Heading2'],
        fontSize=11,
        spaceBefore=12,
        spaceAfter=6,
        textColor=colors.Color(0.2, 0.2, 0.4),
    ))
    styles.add(ParagraphStyle(
        name='CFCBody',
        parent=styles['BodyText'],
        fontSize=10,
        spaceBefore=3,
        spaceAfter=3,
    ))
    styles.add(ParagraphStyle(
        name='CFCCertification',
        parent=styles['BodyText'],
        fontSize=10,
        spaceBefore=6,
        spaceAfter=6,
        borderWidth=1,
        borderColor=colors.black,
        borderPadding=6,
    ))
    styles.add(ParagraphStyle(
        name='CFCFooter',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.grey,
    ))

    story = []

    # Header
    story.append(Paragraph("COURT FILING CERTIFICATE", styles['CFCTitle']))
    story.append(Paragraph("Advanced Electronic Signature Certification", styles['CFCSubtitle']))
    story.append(Paragraph(f"Reference: QSL-{document.id:06d}", styles['CFCSubtitle']))
    story.append(Spacer(1, 0.5*cm))

    # Section 1: Document Particulars
    story.append(Paragraph("1. DOCUMENT PARTICULARS", styles['CFCHeading']))

    doc_data = [
        ["Document Name:", document.original_filename],
        ["File Size:", f"{document.file_size:,} bytes"],
        ["Document Hash:", f"{document.document_hash[:32]}..." if document.document_hash else "N/A"],
        ["Hash Algorithm:", "SHA-256"],
        ["Matter Reference:", document.matter_reference or "Not specified"],
        ["Upload Date:", document.created_at.strftime("%d %B %Y at %H:%M:%S SAST")],
    ]

    doc_table = Table(doc_data, colWidths=[4.5*cm, 11.5*cm])
    doc_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
    ]))
    story.append(doc_table)
    story.append(Spacer(1, 0.3*cm))

    # Section 2: AES Signature Details
    story.append(Paragraph("2. ADVANCED ELECTRONIC SIGNATURE DETAILS", styles['CFCHeading']))

    sig_data = [
        ["Signature Status:", "VALID - Document digitally signed"],
        ["Signing Method:", signature.signing_method],
        ["Signature Algorithm:", signature.signature_algorithm],
        ["Signed At:", signature.signed_at.strftime("%d %B %Y at %H:%M:%S SAST")],
        ["LAWTrust Reference:", signature.lawtrust_reference or "N/A"],
        ["Signed Document Hash:", signature.short_hash],
    ]

    sig_table = Table(sig_data, colWidths=[4.5*cm, 11.5*cm])
    sig_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.9, 1, 0.9)),
    ]))
    story.append(sig_table)
    story.append(Spacer(1, 0.3*cm))

    # Section 3: Certificate Particulars
    story.append(Paragraph("3. CERTIFICATE PARTICULARS", styles['CFCHeading']))

    cert_data = [
        ["Certificate Serial:", certificate.certificate_serial],
        ["Subject:", certificate.subject],
        ["Issuer:", certificate.issuer],
        ["Valid From:", certificate.valid_from.strftime("%d %B %Y")],
        ["Valid Until:", certificate.valid_until.strftime("%d %B %Y")],
        ["Certificate Status:", certificate.status_text],
    ]

    if certificate.is_mock:
        cert_data.append(["Certificate Type:", "MOCK (Development/Testing)"])

    cert_table = Table(cert_data, colWidths=[4.5*cm, 11.5*cm])
    cert_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
    ]))
    story.append(cert_table)
    story.append(Spacer(1, 0.3*cm))

    # Section 4: Service Particulars
    story.append(Paragraph("4. SERVICE PARTICULARS", styles['CFCHeading']))

    service_data = [
        ["Serving Party:", document.sender_name],
        ["Serving Party Email:", document.sender_email],
        ["Recipient:", document.recipient_name or "Not specified"],
        ["Recipient Email:", document.recipient_email],
        ["Service Method:", "Electronic service via QuickServe Legal"],
    ]

    if document.served_at:
        service_data.append(["Served At:", document.served_at.strftime("%d %B %Y at %H:%M:%S SAST")])

    if document.downloaded_at:
        service_data.append(["Received At:", document.downloaded_at.strftime("%d %B %Y at %H:%M:%S SAST")])
        service_data.append(["Receipt Status:", "CONFIRMED - Downloaded by recipient"])
    else:
        service_data.append(["Receipt Status:", "PENDING - Awaiting download"])

    service_table = Table(service_data, colWidths=[4.5*cm, 11.5*cm])
    service_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
    ]))
    story.append(service_table)
    story.append(Spacer(1, 0.3*cm))

    # Section 4B: Email Delivery Tracking (if available)
    if document.email_message_id or document.email_delivered_at:
        story.append(Paragraph("EMAIL DELIVERY CONFIRMATION (ECTA Section 23)", styles['CFCHeading']))

        # Map email status to user-friendly description
        status_map = {
            "pending": "Pending",
            "sent": "Sent",
            "delivered": "DELIVERED to recipient's mail server",
            "opened": "DELIVERED & OPENED by recipient",
            "clicked": "DELIVERED - Recipient clicked link",
            "bounced": "BOUNCED - Delivery failed",
            "failed": "FAILED - Permanent failure",
        }
        email_status_display = status_map.get(
            document.email_status,
            document.email_status.upper() if document.email_status else "Unknown"
        )

        email_data = [
            ["Email Tracking ID:", document.email_message_id or "N/A"],
            ["Delivery Status:", email_status_display],
        ]

        if document.email_delivered_at:
            email_data.append([
                "Delivered to Server:",
                document.email_delivered_at.strftime("%d %B %Y at %H:%M:%S SAST")
            ])

        if document.email_opened_at:
            email_data.append([
                "Opened by Recipient:",
                document.email_opened_at.strftime("%d %B %Y at %H:%M:%S SAST")
            ])

        if document.email_status == "bounced" and document.email_bounce_reason:
            email_data.append(["Bounce Reason:", document.email_bounce_reason])

        email_table = Table(email_data, colWidths=[4.5*cm, 11.5*cm])

        table_style = [
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ]

        # Highlight status row
        if document.is_email_delivered:
            table_style.append(('BACKGROUND', (0, 1), (-1, 1), colors.Color(0.9, 1, 0.9)))
        elif document.email_status == "bounced":
            table_style.append(('BACKGROUND', (0, 1), (-1, 1), colors.Color(1, 0.9, 0.9)))

        email_table.setStyle(TableStyle(table_style))
        story.append(email_table)

    story.append(Spacer(1, 0.5*cm))

    # Section 5: Certification Statement
    story.append(Paragraph("5. CERTIFICATION", styles['CFCHeading']))

    cert_statement = """
    <b>I HEREBY CERTIFY THAT:</b><br/><br/>

    1. The document identified above was digitally signed using an Advanced Electronic Signature (AES)
    in accordance with Section 13 of the Electronic Communications and Transactions Act 25 of 2002 (ECTA).<br/><br/>

    2. The AES was applied using a certificate issued by a recognised certification authority, and the
    private key associated with the certificate was under the sole control of the signatory at the time
    of signing.<br/><br/>

    3. The integrity of the signed document can be verified using the document hash and signature
    details provided in this certificate.<br/><br/>

    4. This certificate is generated automatically by the QuickServe Legal platform and serves as
    prima facie proof of the digital signature and electronic service for court filing purposes.
    """

    story.append(Paragraph(cert_statement, styles['CFCBody']))
    story.append(Spacer(1, 0.5*cm))

    # Legal basis
    story.append(Paragraph("LEGAL BASIS", styles['CFCHeading']))

    legal_text = """
    This Court Filing Certificate is issued in accordance with:
    <br/><br/>
    - Electronic Communications and Transactions Act 25 of 2002 (ECTA), Section 13
    <br/>
    - Uniform Rules of Court, Rule 4A (Electronic Service)
    <br/>
    - Protection of Personal Information Act 4 of 2013 (POPIA)
    """

    story.append(Paragraph(legal_text, styles['CFCBody']))
    story.append(Spacer(1, 1*cm))

    # Footer
    gen_time = format_sast(datetime.utcnow())
    story.append(Paragraph(
        f"<i>This Court Filing Certificate was generated on {gen_time}</i>",
        styles['CFCFooter']
    ))
    story.append(Paragraph(
        f"<i>QuickServe Legal Reference: QSL-{document.id:06d}</i>",
        styles['CFCFooter']
    ))
    story.append(Paragraph(
        "<i>QuickServe Legal (Pty) Ltd - Electronic Service of Legal Documents</i>",
        styles['CFCFooter']
    ))

    # Build PDF
    doc.build(story)

    buffer.seek(0)
    return buffer.getvalue()


def get_court_filing_certificate_filename(document: Document) -> str:
    """Generate filename for Court Filing Certificate PDF."""
    return f"CourtFilingCertificate_QSL-{document.id:06d}.pdf"


def get_placeholder_filename(document: Document) -> str:
    """Generate filename for document with wet-ink placeholder."""
    base_name = Path(document.original_filename).stem
    return f"{base_name}_WITH_SIGNATURE_PAGE.pdf"
