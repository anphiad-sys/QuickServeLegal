# QuickServe Legal - Business Plan

*Created: 29 January 2026*
*Last Updated: 29 January 2026 (Revised pricing: R25.99/doc)*

## Executive Summary

QuickServe Legal is an electronic service platform for South African attorneys to serve legal documents with verified proof of receipt. Unlike email or courier services, QuickServe provides **proof of actual download** - not just delivery - creating an immutable audit trail admissible in court.

---

## 1. Monthly Operating Costs

### 1.1 Infrastructure Costs (Estimated Monthly)

| Service | Provider | Cost (USD) | Cost (ZAR)* |
|---------|----------|------------|-------------|
| **Hosting** | DigitalOcean Droplet (2GB RAM) | $18 | R340 |
| **Database** | PostgreSQL (included on droplet) | $0 | R0 |
| **File Storage** | AWS S3 (first 50GB) | $1.15 | R22 |
| **Email Service** | SendGrid (Essentials 50k/month) | $19.95 | R375 |
| **Domain** | .co.za registration (annual/12) | - | R12 |
| **SSL Certificate** | Let's Encrypt | Free | R0 |
| **Backup Storage** | AWS S3 Glacier | $0.50 | R10 |

*Exchange rate assumed: R18.80/USD*

### 1.2 Cost Projections by Stage

| Stage | Users | Documents/Month | Monthly Cost |
|-------|-------|-----------------|--------------|
| **MVP Launch** | 1-10 | 50-200 | R750 |
| **Early Growth** | 10-50 | 200-1,000 | R1,200 |
| **Growth** | 50-200 | 1,000-5,000 | R2,500 |
| **Scale** | 200-500 | 5,000-15,000 | R5,000 |
| **Mature** | 500+ | 15,000+ | R10,000+ |

### 1.3 Cost Breakdown Notes

**Hosting scales with traffic:**
- Basic (2GB): R340/month - handles ~50 concurrent users
- Standard (4GB): R680/month - handles ~200 concurrent users
- Performance (8GB): R1,360/month - handles ~500+ concurrent users

**Storage costs are minimal:**
- Average legal document: 500KB - 2MB
- 1,000 documents = ~1GB = R0.43/month on S3
- Storage only becomes significant at 100,000+ documents

**Email is the variable cost:**
- SendGrid Free: 100 emails/day (good for MVP)
- SendGrid Essentials: 50,000/month for R375
- Each document service = 2 emails (notification + confirmation)

---

## 2. Revenue Model

### 2.1 Pricing Strategy (FINAL)

#### Pay-As-You-Go (Primary - Low Barrier Entry)
| Model | Price |
|-------|-------|
| **Per document** | **R25.99** |

**Why R25.99:**
- Under the psychological R30 barrier
- 83% cheaper than sheriff (R150-R400)
- Simple, memorable pricing
- Zero commitment - attorneys can try with one document
- Still profitable (break-even at 46 docs/month)

#### Subscription Tiers (For Volume Users)
| Tier | Users | Documents Included | Monthly Price | Effective per Doc |
|------|-------|-------------------|---------------|-------------------|
| **Solo** | 1 | 50 | R249 | R4.98 |
| **Firm** | 10 | 200 | R799 | R4.00 |
| **Enterprise** | Unlimited | 500 | R1,999 | R4.00 |

Additional documents beyond tier: R20 each

**Subscription value proposition:** 80% savings vs pay-as-you-go for regular users

#### Free Trial
- 14 days
- 5 documents included
- No credit card required

### 2.2 Direct Competitor: LegalServe

**LegalServe** is our only direct competitor offering electronic service via platform.

| Aspect | LegalServe | QuickServe (Our Advantage) |
|--------|------------|----------------------------|
| Electronic service | Yes | Yes |
| Proof of download | Unknown | Yes - verified timestamp |
| E-signature on documents | No | **Yes - built-in from launch** |
| Court-ready paragraph | No | **Yes - auto-appended** |
| Wet-ink signature placeholder | No | **Yes - for filing** |
| Customer service | Poor (firsthand experience) | Priority focus |
| Pricing | TBD (research ongoing) | R25.99/doc |

**Competitive Intelligence:**
- VEDlaw is currently a LegalServe client for research purposes
- This allows firsthand observation of their complete model
- Key learnings will inform QuickServe feature development

**Pain points observed with LegalServe:**
- Poor customer service experience
- [Add more observations as discovered]

### 2.3 Alternative Methods (Indirect Competition)

| Method | Cost | Time | Legal Proof |
|--------|------|------|-------------|
| Sheriff service | R150-R400 | 1-5 days | Yes |
| Courier (same-day) | R100-R250 | Same day | Weak |
| Registered mail | R50-R80 | 3-7 days | Weak |
| Email with read receipt | Free | Instant | No |

**QuickServe positioning:** Better than LegalServe + cheaper than physical delivery + legally valid unlike email.

---

## 3. Revenue Projections

### 3.1 Revenue Model Mix (Expected)

Early stage will likely be mostly pay-as-you-go as users try the service:

| Stage | Pay-as-you-go | Subscriptions |
|-------|---------------|---------------|
| Months 1-6 | 70% | 30% |
| Months 7-12 | 50% | 50% |
| Year 2+ | 30% | 70% |

### 3.2 Conservative Scenario (Blended Model)

| Month | Pay-as-you-go Docs | Solo (R249) | Firm (R799) | MRR | ARR |
|-------|-------------------|-------------|-------------|-----|-----|
| 3 | 100 | 3 | 0 | R3,346 | R40,152 |
| 6 | 250 | 10 | 2 | R11,488 | R137,856 |
| 12 | 400 | 25 | 8 | R22,817 | R273,804 |
| 18 | 600 | 50 | 15 | R40,069 | R480,828 |
| 24 | 800 | 80 | 25 | R60,712 | R728,544 |

*Calculations: (Docs × R25.99) + (Solo × R249) + (Firm × R799)*
*MRR = Monthly Recurring Revenue, ARR = Annual Recurring Revenue*

### 3.3 Break-Even Analysis

**Fixed monthly costs (early stage):** R1,200

| Pricing Model | Break-Even Point |
|---------------|------------------|
| R25.99/document only | 46 documents/month |
| R249 Solo subscription only | 5 subscribers |
| Mixed (2 Solo + 30 docs) | R498 + R780 = R1,278 |

**Realistic break-even:** Month 2-3 after launch with minimal marketing.

### 3.4 Profit Projections

| Stage | Monthly Revenue | Monthly Costs | Net Profit | Margin |
|-------|-----------------|---------------|------------|--------|
| Month 6 | R11,488 | R1,500 | R9,988 | 87% |
| Month 12 | R22,817 | R2,500 | R20,317 | 89% |
| Month 24 | R60,712 | R5,000 | R55,712 | 92% |

**Note:** Lower per-document price = more users = faster growth trajectory.
The R25.99 price point removes friction and accelerates adoption.

---

## 4. Key Differentiating Feature: Advanced Electronic Signature

### 4.1 The Problem We Solve

When attorneys serve documents electronically, courts still want to see:
1. Proof that the document was actually received/downloaded
2. A wet-ink signature on the document at filing stage
3. Compliance with Rule 4A requirements

LegalServe and email don't address this properly.

### 4.2 QuickServe's Solution: Document Enhancement Flow

**When an attorney uploads a document for service, QuickServe will:**

```
┌─────────────────────────────────────────────────────────────────┐
│  ORIGINAL DOCUMENT (uploaded by attorney)                       │
│  ─────────────────────────────────────────────────────────────  │
│  [Full pleading/notice content]                                 │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│  AUTO-APPENDED SERVICE PARAGRAPH (QuickServe adds this)         │
│  ─────────────────────────────────────────────────────────────  │
│  "This document was served electronically via QuickServe Legal  │
│   in accordance with Rule 4A of the Uniform Rules of Court.     │
│   Service details:                                              │
│   - Served to: [recipient email]                                │
│   - Date/Time served: [timestamp SAST]                          │
│   - Reference: [QuickServe tracking number]"                    │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│  ADVANCED ELECTRONIC SIGNATURE                                  │
│  ─────────────────────────────────────────────────────────────  │
│  [Digital signature of serving attorney]                        │
│  Signed by: [Attorney name]                                     │
│  Date: [Timestamp]                                              │
│  Certificate: [Signature verification details]                  │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│  WET-INK SIGNATURE PLACEHOLDER (for court filing)               │
│  ─────────────────────────────────────────────────────────────  │
│                                                                 │
│  ________________________                                       │
│  [Attorney name]                                                │
│  [Firm name]                                                    │
│  [Date: _______________]                                        │
│                                                                 │
│  (Space for physical signature when filing with court)          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 4.3 Why This Gives Us an Edge

| Feature | LegalServe | QuickServe |
|---------|------------|------------|
| Service paragraph auto-appended | No | **Yes** |
| Advanced e-signature | No | **Yes** |
| Wet-ink placeholder for filing | No | **Yes** |
| Court clerk acceptance | Unknown | **Designed for it** |

**This is our competitive moat.** Attorneys using QuickServe get:
- Court-ready documents out of the box
- No manual editing needed
- Compliant with clerk expectations
- Professional appearance

### 4.4 Implementation Priority

**This feature should be in MVP** - it's our key differentiator over LegalServe.

---

## 5. Development Timeline

### Phase 1: MVP (Months 1-2) - CURRENT
- [x] Core authentication system
- [x] Document upload functionality
- [x] Secure download with token
- [x] Download tracking & timestamps
- [x] Proof of Service PDF generation
- [x] Email notifications
- [ ] **Advanced e-signature integration**
- [ ] **Auto-append service paragraph to documents**
- [ ] **Wet-ink signature placeholder on documents**
- [ ] Testing & bug fixes
- [ ] Deploy to staging environment

### Phase 2: Beta Launch (Month 3) - WITH E-SIGNATURE
- [ ] Deploy to production (DigitalOcean/AWS)
- [ ] Recruit 3-5 beta testers (friendly firms)
- [ ] Gather feedback and iterate
- [ ] Set up payment integration (PayFast/Yoco)
- [ ] Terms of Service & Privacy Policy (legal review)

### Phase 3: Soft Launch (Month 4)
- [ ] Open registration
- [ ] Implement subscription billing
- [ ] Launch marketing website
- [ ] Begin content marketing (blog)
- [ ] Target: 10 paying customers

### Phase 4: Growth (Months 5-8)
- [ ] Law Society engagement
- [ ] Conference presence
- [ ] Referral programme
- [ ] Feature additions based on feedback
- [ ] Target: 50 paying customers

### Phase 5: Scale (Months 9-12)
- [ ] API for integration with practice management software
- [ ] Bulk upload features
- [ ] Advanced reporting
- [ ] Mobile app (if demand exists)
- [ ] Target: 100+ paying customers

### Phase 6: Expansion (Year 2+)
- [ ] Integration with legal practice management systems
- [ ] Expansion to other document types
- [ ] Potential partnerships with law societies
- [ ] Consider other African markets

---

## 6. Marketing Strategy

### 5.1 Target Market

**Primary:** South African attorneys and law firms
- ~27,000 practising attorneys in South Africa
- ~6,000 law firms
- High concentration in Gauteng, Western Cape, KwaZulu-Natal

**Secondary:** Legal secretaries and paralegals (influence purchase decisions)

**Ideal Customer Profile:**
- Litigation practice (high volume of service)
- 2-20 attorneys
- Tech-forward mindset
- Frustrated with sheriff costs/delays

### 5.2 Marketing Channels

#### Channel 1: Law Society Engagement
- **Law Society of South Africa (LSSA)** - national body
- **Provincial societies:** Cape Law Society, KZN Law Society, Law Society of the Northern Provinces
- **Approach:** Present at CPD events, advertise in newsletters
- **Cost:** R5,000-R15,000 for sponsored content

#### Channel 2: Legal Publications
| Publication | Audience | Ad Cost (estimate) |
|-------------|----------|-------------------|
| **De Rebus** | 25,000+ attorneys | R8,000-R15,000/issue |
| **Without Prejudice** | Legal professionals | R5,000-R10,000 |
| **Legal Brief** | Online newsletter | R2,000-R5,000 |

#### Channel 3: Digital Marketing
- **LinkedIn:** Target attorneys, law firm managers
  - Budget: R3,000-R5,000/month
  - Content: Educational posts about electronic service, Rule 4A
- **Google Ads:** Keywords like "electronic service legal documents"
  - Budget: R2,000-R4,000/month
- **SEO:** Blog content on legal service requirements

#### Channel 4: Direct Outreach
- Personal network (VEDlaw contacts)
- LinkedIn connection requests to litigation attorneys
- Email to law firm managers
- Cost: Time only

#### Channel 5: Referral Programme
- Offer 5 free documents (R130 value) for each referral
- Referred user also gets 5 free documents
- Word-of-mouth is powerful in legal community
- Low R25.99 price makes "just try it" easy to recommend

#### Channel 6: Legal Conferences
| Event | Timing | Cost |
|-------|--------|------|
| LSSA Annual Conference | October | R15,000-R30,000 (exhibitor) |
| Provincial law society events | Various | R3,000-R10,000 |
| Legal Tech Summit | TBD | R10,000-R20,000 |

### 5.3 Marketing Budget by Phase

| Phase | Monthly Budget | Focus |
|-------|---------------|-------|
| Beta (Month 3) | R0 | Personal network only |
| Soft Launch (Month 4) | R2,000 | LinkedIn + content |
| Growth (Months 5-8) | R5,000 | Digital ads + publications |
| Scale (Months 9-12) | R10,000 | Conferences + PR |

### 5.4 Content Marketing Topics

Blog/article ideas to establish authority:
1. "Understanding Rule 4A: Electronic Service of Legal Documents"
2. "Sheriff vs Electronic Service: A Cost Comparison"
3. "ECTA and Electronic Service: What Attorneys Need to Know"
4. "5 Problems with Email Service (and How to Solve Them)"
5. "The Future of Legal Document Delivery in South Africa"

### 5.5 Competitive Positioning

**Message:** "Proof of Download, Not Just Delivery - Only R25.99"

**Key differentiators:**
1. **R25.99** - 83% cheaper than sheriff, zero commitment
2. **Verified receipt** - Know exactly when they downloaded it
3. **Court-ready proof** - PDF proof of service with timestamps
4. **Instant delivery** - No waiting for sheriffs
5. **Audit trail** - Complete history for compliance

**Price comparison for clients:**
| Method | Cost | Time | Legal Proof |
|--------|------|------|-------------|
| Sheriff | R150-R400 | 1-5 days | Yes |
| Courier | R100-R250 | Same day | Weak |
| Email | Free | Instant | No |
| **QuickServe** | **R25.99** | **Instant** | **Yes** |

---

## 7. Risk Analysis

### 6.1 Risks and Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Low adoption | High | Medium | Free trial, education content |
| Competitor entry | Medium | Medium | First-mover advantage, features |
| Legal validity challenged | High | Low | Clear terms, legal opinion |
| Technical failure | High | Low | Backups, monitoring, SLA |
| Regulatory change | Medium | Low | Monitor legal developments |

### 6.2 Legal Considerations

- Rule 4A explicitly allows electronic service for subsequent documents
- ECTA provides framework for electronic communications
- Need clear Terms of Service drafted by attorney
- Consider professional indemnity implications

---

## 8. Key Metrics to Track

### 7.1 Growth Metrics
- Monthly Recurring Revenue (MRR)
- Number of active subscribers
- Documents served per month
- New signups per week

### 7.2 Engagement Metrics
- Documents served per user per month
- Download rate (% of documents actually downloaded)
- Time to download (how quickly recipients download)
- User retention rate (monthly/annual)

### 7.3 Business Health
- Customer Acquisition Cost (CAC)
- Lifetime Value (LTV)
- Churn rate
- Net Promoter Score (NPS)

---

## 9. Summary

### Final Pricing
| Model | Price |
|-------|-------|
| **Pay-as-you-go** | **R25.99/document** |
| Solo subscription (50 docs) | R249/month |
| Firm subscription (200 docs) | R799/month |

### Investment Required
| Item | Cost |
|------|------|
| Development | Time (already invested) |
| First 6 months hosting/services | R7,500 |
| Initial marketing | R10,000 |
| Legal (Terms, Privacy Policy) | R5,000-R10,000 |
| **Total to Launch** | **R22,500-R27,500** |

### Projected Returns (with R25.99 pricing)
| Timeframe | Monthly Revenue | Monthly Profit |
|-----------|-----------------|----------------|
| 6 months | R11,488 | R9,988 |
| 12 months | R22,817 | R20,317 |
| 24 months | R60,712 | R55,712 |

### Why R25.99 Works
- **83% cheaper** than sheriff service
- **Under R30** psychological barrier
- **Zero commitment** - try with one document
- **Break-even** at just 46 documents/month
- **Faster adoption** = larger user base = more referrals

### Next Steps
1. Complete MVP testing
2. Deploy to production
3. Recruit beta testers
4. Set up payment processing (PayFast/Yoco)
5. Draft Terms of Service
6. Soft launch

---

*This document should be updated as assumptions are validated and market feedback is received.*
