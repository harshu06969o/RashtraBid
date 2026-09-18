"""
GeM-Guard Demo PDF Generator
Generates two realistic PDFs:
  1. tender_GEM_2026_B_4521001.pdf  -- Government tender document with all 5 eligibility clauses
  2. bid_infralink_B.pdf            -- Bidder B (Infralink Technologies) bid package with CA certificate

Both PDFs contain real text that the GeM-Guard extraction pipeline can parse.
"""

from pathlib import Path
from fpdf import FPDF

OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "sample_docs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ── Helpers ────────────────────────────────────────────────────────────────────

class GemPDF(FPDF):
    def __init__(self, doc_type="TENDER"):
        super().__init__()
        self.doc_type = doc_type
        self.set_auto_page_break(auto=True, margin=20)
        self.set_margins(20, 20, 20)

    def header(self):
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(80, 80, 80)
        if self.doc_type == "TENDER":
            self.cell(0, 8, "GOVERNMENT e-MARKETPLACE (GeM) | TENDER DOCUMENT | GEM/2026/B/4521001", align="C")
        else:
            self.cell(0, 8, "BID PACKAGE -- INFRALINK TECHNOLOGIES LIMITED | GEM/2026/B/4521001", align="C")
        self.ln(2)
        self.set_draw_color(30, 58, 95)
        self.set_line_width(0.5)
        self.line(20, self.get_y(), 190, self.get_y())
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 8, f"Page {self.page_no()} | GeM-Guard Demo Document -- NOT FOR OFFICIAL USE", align="C")

    def section_title(self, text):
        self.ln(4)
        self.set_font("Helvetica", "B", 12)
        self.set_fill_color(30, 58, 95)
        self.set_text_color(255, 255, 255)
        self.cell(0, 8, f"  {text}", fill=True, ln=True)
        self.set_text_color(0, 0, 0)
        self.ln(2)

    def clause_title(self, number, title):
        self.ln(3)
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(30, 58, 95)
        self.cell(0, 6, f"Clause {number}: {title}", ln=True)
        self.set_text_color(0, 0, 0)
        self.ln(1)

    def body(self, text, indent=0):
        self.set_font("Helvetica", "", 9.5)
        self.set_left_margin(20 + indent)
        self.multi_cell(0, 5.5, text)
        self.set_left_margin(20)
        self.ln(1)

    def field_row(self, label, value, bold_value=False):
        self.set_font("Helvetica", "B", 9)
        self.cell(60, 6, label + ":", ln=False)
        self.set_font("Helvetica", "B" if bold_value else "", 9)
        self.cell(0, 6, value, ln=True)

    def divider(self):
        self.ln(2)
        self.set_draw_color(200, 200, 200)
        self.line(20, self.get_y(), 190, self.get_y())
        self.ln(3)

    def notice_box(self, text, color=(255, 243, 205)):
        self.set_fill_color(*color)
        self.set_font("Helvetica", "I", 9)
        self.set_left_margin(20)
        self.multi_cell(0, 5.5, text, fill=True, border=1)
        self.ln(2)


# ── TENDER DOCUMENT ────────────────────────────────────────────────────────────

def generate_tender():
    pdf = GemPDF(doc_type="TENDER")
    pdf.add_page()

    # Cover
    pdf.ln(6)
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(30, 58, 95)
    pdf.cell(0, 10, "GOVERNMENT e-MARKETPLACE", align="C", ln=True)
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, "Request for Proposal (RFP)", align="C", ln=True)
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(60, 60, 60)
    pdf.cell(0, 7, "IT Infrastructure Modernisation -- Phase II", align="C", ln=True)
    pdf.ln(6)

    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(0, 0, 0)
    details = [
        ("Tender Reference Number", "GEM/2026/B/4521001"),
        ("Issuing Authority", "Ministry of Electronics and Information Technology (MeitY)"),
        ("Procurement Category", "IT Services -- Category B"),
        ("Estimated Contract Value", "INR 85,00,00,000 (Rupees Eighty-Five Crore)"),
        ("Bid Submission Deadline", "15 October 2026, 17:00 hrs IST"),
        ("Technical Bid Opening", "17 October 2026, 11:00 hrs IST"),
        ("EMD Amount", "INR 85,00,000 (Rupees Eighty-Five Lakh)"),
        ("Validity of Bid", "180 days from submission deadline"),
    ]
    for label, value in details:
        pdf.field_row(label, value)

    pdf.ln(4)
    pdf.notice_box(
        "  IMPORTANT: This tender is issued on the GeM portal. All bids must be submitted electronically "
        "through https://gem.gov.in. Physical bids will NOT be accepted. "
        "Bidders are advised to read the entire document carefully before submission.",
        color=(219, 234, 254)
    )

    # Section 1
    pdf.section_title("SECTION 1 -- SCOPE OF WORK")
    pdf.body(
        "The Ministry of Electronics and Information Technology (MeitY) invites bids from eligible firms "
        "for the supply, installation, commissioning and maintenance of IT infrastructure components "
        "including servers, networking equipment, storage systems, and associated software licenses "
        "for government data centres across 12 states.\n\n"
        "The successful bidder shall be responsible for:\n"
        "  (a) Procurement and delivery of hardware as per technical specifications\n"
        "  (b) Installation and commissioning at designated sites\n"
        "  (c) Integration with existing NICNET infrastructure\n"
        "  (d) 5-year Annual Maintenance Contract (AMC)\n"
        "  (e) Training of government technical staff\n"
        "  (f) Compliance with all applicable Indian data protection regulations"
    )

    # Section 2
    pdf.section_title("SECTION 2 -- GENERAL INSTRUCTIONS TO BIDDERS")
    pdf.body(
        "2.1  All bids shall be submitted in the prescribed format on GeM portal only.\n"
        "2.2  The bid shall remain valid for 180 days from the last date of submission.\n"
        "2.3  Bids submitted after the deadline will be summarily rejected.\n"
        "2.4  The procuring entity reserves the right to cancel the tender at any stage.\n"
        "2.5  All costs related to preparation and submission of bid shall be borne by the bidder.\n"
        "2.6  The bidder shall not have any conflict of interest with other bidders.\n"
        "2.7  Canvassing in any form will lead to disqualification of the bid.\n"
        "2.8  All disputes shall be subject to jurisdiction of courts in New Delhi."
    )

    # Section 3 -- ELIGIBILITY (most important -- extractable)
    pdf.add_page()
    pdf.section_title("SECTION 3 -- ELIGIBILITY CRITERIA (TECHNICAL QUALIFICATION)")

    pdf.notice_box(
        "  All eligibility criteria must be met as on the date of bid submission. "
        "Non-compliance with any mandatory criterion will result in rejection of the bid "
        "without further evaluation. The compliance engine will verify each criterion against "
        "submitted documentary evidence.",
        color=(254, 243, 205)
    )

    pdf.clause_title("3.1", "Financial Eligibility -- Minimum Annual Turnover")
    pdf.body(
        "The bidder must have an average annual turnover of not less than Rs. 10 Crore "
        "(Rupees Ten Crore only) during the last three financial years "
        "(FY 2022-23, FY 2023-24, FY 2024-25), as certified by a Chartered Accountant.\n\n"
        "Supporting Documents Required:\n"
        "  (a) CA Certificate (original, signed and stamped) certifying the average annual turnover\n"
        "  (b) Audited Balance Sheets for FY 2022-23, FY 2023-24, FY 2024-25\n"
        "  (c) Profit and Loss Accounts for corresponding financial years\n\n"
        "Note: In case of consortium, the lead member alone must satisfy this criterion. "
        "Turnover of subsidiaries or group companies shall not be considered."
    )
    pdf.divider()

    pdf.clause_title("3.2", "GST Registration Status")
    pdf.body(
        "The bidder shall be registered under the Goods and Services Tax (GST) Act, 2017, "
        "and the GST registration status must be ACTIVE as of the date of bid submission.\n\n"
        "Supporting Documents Required:\n"
        "  (a) GST Registration Certificate (Form REG-06) showing ACTIVE status\n"
        "  (b) Latest GST return filing acknowledgement (GSTR-3B) for the preceding quarter\n\n"
        "Bidders whose GST registration is suspended, cancelled, or shows any status other than "
        "ACTIVE shall be disqualified from participation."
    )
    pdf.divider()

    pdf.clause_title("3.3", "MSME / Udyam Registration (for MSME bidders)")
    pdf.body(
        "MSME bidders must hold a valid Udyam Registration Certificate issued by the "
        "Ministry of Micro, Small and Medium Enterprises. The Udyam Registration Number (URN) "
        "must be valid and active as on the bid submission date.\n\n"
        "Supporting Documents Required:\n"
        "  (a) Udyam Registration Certificate with QR code\n"
        "  (b) Udyam Registration Number (format: UDYAM-XX-00-XXXXXXX)\n\n"
        "Large enterprises (non-MSME) are exempt from this requirement. "
        "MSME bidders may be entitled to benefits under the Public Procurement Policy for MSEs, 2012."
    )
    pdf.divider()

    pdf.clause_title("3.4", "Statutory Certificate Validity")
    pdf.body(
        "All statutory certificates submitted must be valid as on the bid submission date. "
        "Expired certificates will not be accepted and will be treated as non-compliant.\n\n"
        "The following certificates must be current and unexpired:\n"
        "  (a) GST Registration Certificate\n"
        "  (b) Udyam Registration Certificate (if applicable)\n"
        "  (c) Digital Signature Certificate (DSC) of authorised signatory\n"
        "  (d) ISO/Quality certifications (if claimed for evaluation)\n\n"
        "Validity will be verified against the expiry dates printed on each certificate. "
        "The procuring entity may also verify validity through official government portals."
    )
    pdf.divider()

    pdf.clause_title("3.5", "Entity Name Consistency Across Documents")
    pdf.body(
        "The legal entity name must be consistent across all submitted documents including "
        "the incorporation certificate, GST registration, PAN card, Udyam registration, "
        "bid form, and CA certificate.\n\n"
        "Acceptable variations:\n"
        "  - 'Private Limited' may be abbreviated as 'Pvt. Ltd.' or 'P. Ltd.'\n"
        "  - 'Limited' may be abbreviated as 'Ltd.'\n\n"
        "Inconsistencies in entity name that suggest different legal entities will require "
        "clarification before the bid can proceed to evaluation. "
        "Bids where name inconsistency cannot be resolved will be marked for officer review."
    )

    # Section 4
    pdf.add_page()
    pdf.section_title("SECTION 4 -- TECHNICAL SPECIFICATIONS")
    pdf.body(
        "4.1  Server Requirements:\n"
        "     - Minimum 32-core processor, 256 GB RAM, 10 TB NVMe storage\n"
        "     - Dual redundant power supply, hot-swappable drives\n"
        "     - IPMI/BMC remote management capability\n\n"
        "4.2  Networking Equipment:\n"
        "     - Core switches: 48-port 10GbE + 4x 100GbE uplink\n"
        "     - Firewall: Next-generation with IPS/IDS capability\n"
        "     - Load balancer: Layer 7 with SSL offloading\n\n"
        "4.3  Software Requirements:\n"
        "     - Operating System: RHEL 9.x or equivalent government-approved Linux distribution\n"
        "     - Hypervisor: VMware vSphere or KVM-based solution\n"
        "     - Backup solution: Enterprise-grade with 3-2-1 rule compliance\n\n"
        "4.4  Security Requirements:\n"
        "     - VAPT certification from CERT-IN empanelled agency\n"
        "     - End-to-end encryption for data in transit and at rest\n"
        "     - Compliance with MEITY cybersecurity framework"
    )

    # Section 5
    pdf.section_title("SECTION 5 -- EVALUATION METHODOLOGY")
    pdf.body(
        "5.1  Two-Bid System: Technical and Financial bids to be submitted separately.\n\n"
        "5.2  Technical Evaluation (Pass/Fail):\n"
        "     All mandatory eligibility criteria (Section 3) will be evaluated on pass/fail basis.\n"
        "     Bids failing any mandatory criterion will be rejected without financial evaluation.\n\n"
        "5.3  Financial Evaluation:\n"
        "     L1 (lowest cost) methodology will be applied among technically qualified bids.\n\n"
        "5.4  Integrity Pact:\n"
        "     All bidders must sign the Integrity Pact as per CVC guidelines.\n\n"
        "5.5  Negotiations:\n"
        "     Procuring entity reserves the right to negotiate with L1 bidder."
    )

    # Section 6
    pdf.section_title("SECTION 6 -- TERMS AND CONDITIONS")
    pdf.body(
        "6.1  Payment Terms: 30% advance on contract signing, 60% on delivery and commissioning, "
        "10% after 6-month defect liability period.\n\n"
        "6.2  Liquidated Damages: 0.5% of contract value per week of delay, maximum 10%.\n\n"
        "6.3  Performance Security: 3% of contract value, valid for 18 months from delivery.\n\n"
        "6.4  Governing Law: Laws of India. Arbitration as per Arbitration and Conciliation Act, 1996.\n\n"
        "6.5  Force Majeure: Standard GoI clauses apply.\n\n"
        "6.6  Amendments: Any corrigendum will be published on GeM portal only. "
        "Bidders are advised to check the portal regularly for updates."
    )

    out = str(OUTPUT_DIR / "tender_GEM_2026_B_4521001.pdf")
    pdf.output(out)
    print(f"[OK] Tender PDF: {out}")
    return out


# ── BIDDER DOCUMENT (Bid Package for Bidder B -- Infralink Technologies) ──────

def generate_bid():
    pdf = GemPDF(doc_type="BID")
    pdf.add_page()

    # Cover
    pdf.ln(6)
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(30, 58, 95)
    pdf.cell(0, 9, "BID SUBMISSION PACKAGE", align="C", ln=True)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 7, "Technical Bid -- Eligibility Documents", align="C", ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(60, 60, 60)
    pdf.cell(0, 6, "Tender Reference: GEM/2026/B/4521001", align="C", ln=True)
    pdf.ln(6)

    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(0, 0, 0)
    details = [
        ("Bidder Name",           "Infralink Technologies Limited"),
        ("Legal Entity Name",     "Infralink Technologies Limited"),
        ("Registered Office",     "Plot No. 45-B, Okhla Industrial Estate, Phase III, New Delhi -- 110020"),
        ("CIN",                   "U72900DL2011PLC218456"),
        ("PAN",                   "AACCI4520M"),
        ("GSTIN",                 "07AACCI4520M1ZP"),
        ("Udyam Reg. Number",     "UDYAM-DL-03-0067891"),
        ("Contact Person",        "Rajesh Kumar Sharma, Director"),
        ("Email",                 "bids@infralink-tech.in"),
        ("Phone",                 "+91 11 4123 7890"),
        ("Date of Submission",    "12 October 2026"),
    ]
    for label, value in details:
        pdf.field_row(label, value)

    pdf.ln(4)
    pdf.notice_box(
        "  This bid is submitted in response to Tender GEM/2026/B/4521001 issued by MeitY. "
        "All documents enclosed are true copies of originals. The bidder accepts all terms "
        "and conditions of the tender document without any deviation.",
        color=(219, 234, 254)
    )

    # Doc index
    pdf.section_title("DOCUMENT INDEX")
    pdf.set_font("Helvetica", "", 9.5)
    docs = [
        ("1", "Bid Cover Letter and Declaration",           "Page 2"),
        ("2", "CA Certificate -- Average Annual Turnover",   "Page 3-4"),
        ("3", "Audited Financial Statements FY 2024-25",    "Page 5-7"),
        ("4", "GST Registration Certificate",               "Page 8"),
        ("5", "Udyam Registration Certificate",             "Page 9"),
        ("6", "Company Incorporation Certificate",          "Page 10"),
        ("7", "Board Resolution for Bid Authorisation",     "Page 11"),
        ("8", "Integrity Pact (signed)",                    "Page 12"),
    ]
    for num, title, page in docs:
        pdf.cell(12, 6, num + ".", ln=False)
        pdf.cell(130, 6, title, ln=False)
        pdf.cell(0, 6, page, ln=True)

    # Page 2 -- Cover Letter
    pdf.add_page()
    pdf.section_title("DOCUMENT 1 -- BID COVER LETTER AND DECLARATION")
    pdf.ln(2)
    pdf.body(
        "To,\n"
        "The Tender Evaluation Committee\n"
        "Ministry of Electronics and Information Technology\n"
        "Electronics Niketan, 6, CGO Complex\n"
        "New Delhi -- 110003\n\n"
        "Subject: Submission of Technical Bid for Tender GEM/2026/B/4521001\n\n"
        "Dear Sir/Madam,\n\n"
        "We, Infralink Technologies Limited, hereby submit our technical bid for the above-referenced "
        "tender for IT Infrastructure Modernisation -- Phase II.\n\n"
        "We confirm that:\n"
        "  1. We have read and understood all terms and conditions of the tender document.\n"
        "  2. All eligibility criteria as specified in Section 3 are met by our organisation.\n"
        "  3. All documents submitted are genuine and verifiable.\n"
        "  4. We have not been blacklisted by any government authority in India.\n"
        "  5. We accept the evaluation methodology as specified in the tender.\n\n"
        "Authorised Signatory: Rajesh Kumar Sharma\n"
        "Designation: Managing Director\n"
        "Date: 12 October 2026\n"
        "Place: New Delhi"
    )

    # Page 3-4 -- CA Certificate (KEY PAGE for extraction)
    pdf.add_page()
    pdf.section_title("DOCUMENT 2 -- CA CERTIFICATE: AVERAGE ANNUAL TURNOVER")
    pdf.ln(3)

    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(30, 58, 95)
    pdf.cell(0, 7, "CERTIFICATE OF AVERAGE ANNUAL TURNOVER", align="C", ln=True)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 5, "(As required under Clause 3.1 of Tender GEM/2026/B/4521001)", align="C", ln=True)
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 6, "CHARTERED ACCOUNTANT DETAILS:", ln=True)
    ca_details = [
        ("CA Name",           "CA Priya Venkataraman"),
        ("Membership Number", "M-214876 (ICAI)"),
        ("Firm Name",         "Venkataraman & Associates, Chartered Accountants"),
        ("Firm Reg. Number",  "FRN 009876N"),
        ("Office Address",    "201, Ansal Chambers-I, 3 Bhikaji Cama Place, New Delhi -- 110066"),
        ("Certificate Date",  "10 October 2026"),
        ("Certificate No.",   "VA/TUR/2026/INF/089"),
    ]
    for label, value in ca_details:
        pdf.field_row(label, value)

    pdf.ln(4)
    pdf.set_font("Helvetica", "", 9.5)
    pdf.multi_cell(0, 5.5,
        "This is to certify that I have examined the books of accounts and financial records of "
        "INFRALINK TECHNOLOGIES LIMITED (CIN: U72900DL2011PLC218456), having its registered office at "
        "Plot No. 45-B, Okhla Industrial Estate, Phase III, New Delhi -- 110020.\n\n"
        "Based on my examination of the audited financial statements and books of accounts, "
        "I hereby certify the following Average Annual Turnover for the last three financial years:"
    )

    # THE KEY TABLE -- extraction pipeline will read these numbers
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(30, 58, 95)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(70, 7, "  Financial Year", fill=True, border=1, ln=False)
    pdf.cell(60, 7, "Annual Turnover (INR)", fill=True, border=1, ln=False)
    pdf.cell(0,  7, "Remarks", fill=True, border=1, ln=True)

    pdf.set_font("Helvetica", "", 9.5)
    pdf.set_text_color(0, 0, 0)
    rows = [
        ("FY 2022-23 (April 2022 -- March 2023)", "Rs. 7,90,00,000",  "Audited"),
        ("FY 2023-24 (April 2023 -- March 2024)", "Rs. 8,50,00,000",  "Audited"),
        ("FY 2024-25 (April 2024 -- March 2025)", "Rs. 9,70,00,000",  "Audited"),
    ]
    for fy, amount, remark in rows:
        pdf.cell(70, 6, f"  {fy}", border=1, ln=False)
        pdf.cell(60, 6, f"  {amount}", border=1, ln=False)
        pdf.cell(0,  6, f"  {remark}", border=1, ln=True)

    # Average row -- THE CRITICAL LINE
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(254, 243, 205)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(70, 8, "  AVERAGE ANNUAL TURNOVER", fill=True, border=1, ln=False)
    pdf.cell(60, 8, "  Rs. 8,70,00,000  (Rs. 8.7 Crore)", fill=True, border=1, ln=False)
    pdf.cell(0,  8, "  CERTIFIED", fill=True, border=1, ln=True)

    pdf.ln(4)
    pdf.set_font("Helvetica", "", 9.5)
    pdf.multi_cell(0, 5.5,
        "The Average Annual Turnover of Infralink Technologies Limited for the three financial years "
        "FY 2022-23, FY 2023-24, and FY 2024-25 is Rs. 8,70,00,000 (Rupees Eight Crore Seventy Lakh only), "
        "which is equivalent to Rs. 8.7 Crore.\n\n"
        "This certificate is issued at the request of the company for submission to the Ministry of "
        "Electronics and Information Technology in response to Tender GEM/2026/B/4521001.\n\n"
        "I confirm that this certificate is based on audited financial statements and the books of "
        "accounts maintained in accordance with the Companies Act, 2013, and applicable Accounting Standards."
    )
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 5, "Signature of Chartered Accountant:", ln=True)
    pdf.ln(8)
    pdf.set_draw_color(0, 0, 0)
    pdf.line(20, pdf.get_y(), 90, pdf.get_y())
    pdf.ln(1)
    pdf.set_font("Helvetica", "", 8)
    pdf.cell(0, 4, "CA Priya Venkataraman | M-214876 | Venkataraman & Associates", ln=True)
    pdf.cell(0, 4, "Date: 10 October 2026 | Place: New Delhi", ln=True)
    pdf.cell(0, 4, "[ICAI Membership Stamp]", ln=True)

    # Page 4 -- Financial Summary
    pdf.add_page()
    pdf.section_title("DOCUMENT 3 -- FINANCIAL SUMMARY (FY 2024-25)")
    pdf.body(
        "The following is an extract from the Audited Balance Sheet and Profit & Loss Account "
        "of Infralink Technologies Limited for FY 2024-25 (April 2024 -- March 2025)."
    )
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, "PROFIT AND LOSS ACCOUNT EXTRACT -- FY 2024-25", ln=True)
    pdf.ln(1)
    fin_rows = [
        ("Revenue from Operations (Gross Turnover)", "Rs. 9,70,00,000"),
        ("Other Income",                              "Rs. 12,45,000"),
        ("Total Income",                              "Rs. 9,82,45,000"),
        ("Employee Benefit Expenses",                 "Rs. 4,35,20,000"),
        ("Operating Expenses",                        "Rs. 3,87,65,000"),
        ("Depreciation",                              "Rs. 43,10,000"),
        ("Finance Costs",                             "Rs. 28,90,000"),
        ("Profit Before Tax (PBT)",                   "Rs. 87,60,000"),
        ("Tax Expense",                               "Rs. 22,10,000"),
        ("Profit After Tax (PAT)",                    "Rs. 65,50,000"),
    ]
    pdf.set_font("Helvetica", "", 9.5)
    for label, value in fin_rows:
        pdf.cell(120, 6, label, border="B", ln=False)
        pdf.cell(0,   6, value, border="B", ln=True)
    pdf.ln(4)
    pdf.body("Note: Audited by Venkataraman & Associates, Chartered Accountants (FRN 009876N). "
             "Audit Report dated 28 September 2025.")

    # Page 5 -- GST Certificate
    pdf.add_page()
    pdf.section_title("DOCUMENT 4 -- GST REGISTRATION CERTIFICATE")
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(30, 58, 95)
    pdf.cell(0, 7, "GOODS AND SERVICES TAX REGISTRATION CERTIFICATE", align="C", ln=True)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 5, "(Form GST REG-06)", align="C", ln=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)
    gst_details = [
        ("GSTIN",                      "07AACCI4520M1ZP"),
        ("Legal Name of Business",     "INFRALINK TECHNOLOGIES LIMITED"),
        ("Trade Name",                 "Infralink Technologies"),
        ("Constitution of Business",   "Private Limited Company"),
        ("Date of Liability",          "01 July 2017"),
        ("Date of Registration",       "12 July 2017"),
        ("GSTIN Status",               "ACTIVE"),
        ("Type of Registration",       "Regular"),
        ("State / UT",                 "Delhi (State Code: 07)"),
        ("Principal Place of Business","Plot No. 45-B, Okhla Industrial Estate, Phase III, New Delhi -- 110020"),
        ("Nature of Business Activity","IT Services and Software Development"),
    ]
    pdf.set_font("Helvetica", "B", 9)
    for label, value in gst_details:
        pdf.field_row(label, value, bold_value=(label == "GSTIN Status"))
    pdf.ln(4)
    pdf.notice_box(
        "  GST Registration Status: ACTIVE\n"
        "  This certificate is system-generated from the GST Portal (www.gst.gov.in).\n"
        "  Last verified: 10 October 2026",
        color=(220, 252, 231)
    )

    # Page 6 -- Udyam Certificate
    pdf.add_page()
    pdf.section_title("DOCUMENT 5 -- UDYAM REGISTRATION CERTIFICATE")
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(30, 58, 95)
    pdf.cell(0, 7, "UDYAM REGISTRATION CERTIFICATE", align="C", ln=True)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 5, "(Ministry of Micro, Small and Medium Enterprises, Government of India)", align="C", ln=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)
    udyam_details = [
        ("Udyam Registration Number",  "UDYAM-DL-03-0067891"),
        ("Name of Enterprise",         "INFRALINK TECHNOLOGIES LIMITED"),
        ("Type of Enterprise",         "Small Enterprise"),
        ("Date of Registration",       "15 June 2020"),
        ("Social Category",            "General"),
        ("Activities",                 "Service: IT Services, Software Development, Consulting"),
        ("NIC Code",                   "62011 -- Computer Programming Activities"),
        ("Investment in P&M (Rs. Cr)", "2.45"),
        ("Turnover (Rs. Cr)",          "8.70"),
        ("Status",                     "ACTIVE"),
    ]
    pdf.set_font("Helvetica", "B", 9)
    for label, value in udyam_details:
        pdf.field_row(label, value, bold_value=(label in ("Status", "Udyam Registration Number")))
    pdf.ln(4)
    pdf.notice_box(
        "  Udyam Registration Status: ACTIVE\n"
        "  This certificate is auto-generated from the Udyam Registration Portal.\n"
        "  Registration is valid and there is no expiry for Udyam Certificates.\n"
        "  Verify at: https://udyamregistration.gov.in",
        color=(220, 252, 231)
    )

    out = str(OUTPUT_DIR / "bid_infralink_B_GEM_2026_B_4521001.pdf")
    pdf.output(out)
    print(f"[OK] Bid PDF:    {out}")
    return out


if __name__ == "__main__":
    t = generate_tender()
    b = generate_bid()
    print(f"\nFiles saved in: {OUTPUT_DIR.resolve()}")
    print("\nExtraction hints:")
    print("  Tender: Pattern compiler will find 'Rs. 10 Crore' → REQ-001 TURNOVER >= 10.0")
    print("  Bid:    Evidence extractor will find 'Rs. 8.7 Crore' on Page 4 → FAIL (8.7 < 10)")

