# 📋 MANDATORY DOCUMENT CHECKLIST FOR HRMS

## Overview
This document outlines the mandatory documents required for all employees in the Nexteons HRMS system. These documents ensure compliance with Indian labor laws, tax regulations, and organizational policies.

---

## 🆔 **1. IDENTITY & TAX COMPLIANCE**

### **Aadhaar Card**
- **Purpose:** Essential for UAN (Universal Account Number) linking and identity verification
- **Required For:**
  - Provident Fund (EPF) registration
  - Government identity verification
  - Statutory compliance
- **Document Type:** `AADHAAR`
- **Expiry:** No expiry
- **Format:** PDF/Image (scanned copy)
- **Storage:** Encrypted in secure document vault

### **PAN Card**
- **Purpose:** Mandatory for salary processing and tax (TDS) filings
- **Required For:**
  - Income tax deduction at source (TDS)
  - Salary processing
  - Form 16 generation
  - Annual tax filings
- **Document Type:** `PAN`
- **Expiry:** No expiry
- **Format:** PDF/Image (scanned copy)
- **Storage:** Encrypted in secure document vault

---

## 🎓 **2. EDUCATION VERIFICATION**

### **Highest Qualification Degree/Certificate**
- **Purpose:** Proof of the most recent academic achievement
- **Required For:**
  - Employment verification
  - Role eligibility confirmation
  - Background verification
- **Document Type:** `DEGREE`
- **Expiry:** No expiry
- **Format:** PDF (scanned copy of original)
- **Notes:** 
  - Must be from a recognized university/institution
  - Should match the qualification mentioned in resume

### **Final Semester Marksheet**
- **Purpose:** Usually required if the degree certificate is still pending
- **Required For:**
  - Provisional employment (until degree is issued)
  - Academic performance verification
- **Document Type:** `MARKSHEET`
- **Expiry:** No expiry
- **Format:** PDF (scanned copy)
- **Notes:**
  - Can be replaced with degree certificate once available
  - Must show final semester/year results

---

## 💼 **3. PREVIOUS EMPLOYMENT** (For Lateral Hires)

### **Relieving Letter**
- **Purpose:** Legal proof that the employee has no active obligations to their previous employer
- **Required For:**
  - Background verification
  - Confirming no conflict of interest
  - Legal compliance
- **Document Type:** `RELIEVING`
- **Expiry:** No expiry
- **Format:** PDF (on company letterhead)
- **Notes:**
  - Must be on official letterhead
  - Should include last working date
  - Must be signed by authorized signatory

### **Last 3 Months' Payslips**
- **Purpose:** To verify salary history and calculate professional tax and income tax
- **Required For:**
  - Salary negotiation verification
  - Tax calculation for current financial year
  - Professional tax computation
- **Document Type:** `PAYSLIPS`
- **Expiry:** No expiry
- **Format:** PDF (3 consecutive months)
- **Notes:**
  - Must be from immediate previous employer
  - Should show salary breakup clearly
  - Required for mid-year joiners

### **Form 16 / Digital Tax Summary**
- **Purpose:** Necessary for the finance team to calculate accurate tax deductions for the current financial year
- **Required For:**
  - Accurate TDS calculation
  - Avoiding excess tax deduction
  - Annual tax filing (ITR)
- **Document Type:** `FORM16`
- **Expiry:** Valid for the financial year mentioned
- **Format:** PDF (digitally signed)
- **Notes:**
  - Required from previous employer
  - Must be for the current financial year
  - Helps in tax planning

---

## 🏦 **4. BANKING & STATUTORY**

### **Cancelled Cheque or Bank Passbook**
- **Purpose:** Must clearly show the Account Number and IFSC Code to ensure salary is credited to the correct account
- **Required For:**
  - Salary credit setup
  - Bank account verification
  - Direct deposit configuration
- **Document Type:** `BANK_PROOF`
- **Expiry:** No expiry (but must be current account)
- **Format:** PDF/Image
- **Requirements:**
  - Must clearly show:
    - Account holder name
    - Account number
    - IFSC code
    - Bank name and branch
  - Cancelled cheque should have "CANCELLED" written across
  - Bank passbook first page is acceptable alternative

### **EPF Form 11**
- **Purpose:** A self-declaration form for the Employees' Provident Fund
- **Required For:**
  - EPF account creation/transfer
  - UAN activation
  - Provident fund compliance
- **Document Type:** `EPF_FORM`
- **Expiry:** No expiry
- **Format:** PDF (filled and signed)
- **Notes:**
  - Must be filled completely
  - Requires employee signature
  - Needed for EPF registration

---

## 📂 **5. DOCUMENT MANAGEMENT IN HRMS**

### **Upload Process:**
1. Navigate to **Documents** section
2. Click **Upload Document**
3. Select appropriate document type from dropdown
4. Upload file (PDF/Image, max 5MB)
5. Add issue date and expiry date (if applicable)
6. Submit

### **Document Status:**
- **Valid** - Document is current and accepted
- **Expired** - Document has passed expiry date
- **Renewal in Progress** - Document is being renewed
- **Archived** - Old/replaced document

### **Security Features:**
- All documents stored in encrypted format
- Access restricted to HR, Admin, and document owner
- Audit trail for all document access
- Automatic expiry notifications (30 days before)

---

## ⚠️ **COMPLIANCE NOTES**

### **For New Joiners:**
- All documents must be submitted within **7 days** of joining
- Salary processing may be delayed if mandatory documents are missing
- Provisional documents accepted with commitment to submit originals

### **For Existing Employees:**
- Update expired documents immediately
- Respond to expiry notifications promptly
- Keep digital copies updated

### **For HR Team:**
- Verify all documents within 3 working days
- Send reminders for missing documents
- Maintain document checklist for each employee
- Generate compliance reports monthly

---

## 📊 **DOCUMENT CHECKLIST SUMMARY**

| Category | Document | Code | Mandatory | Expiry |
|----------|----------|------|-----------|--------|
| **Identity & Tax** | Aadhaar Card | `AADHAAR` | ✅ Yes | No |
| **Identity & Tax** | PAN Card | `PAN` | ✅ Yes | No |
| **Education** | Degree Certificate | `DEGREE` | ✅ Yes | No |
| **Education** | Final Marksheet | `MARKSHEET` | ⚠️ If degree pending | No |
| **Previous Employment** | Relieving Letter | `RELIEVING` | ✅ For lateral hires | No |
| **Previous Employment** | Last 3 Payslips | `PAYSLIPS` | ✅ For lateral hires | No |
| **Previous Employment** | Form 16 | `FORM16` | ✅ For mid-year joiners | Yes |
| **Banking** | Cancelled Cheque | `BANK_PROOF` | ✅ Yes | No |
| **Statutory** | EPF Form 11 | `EPF_FORM` | ✅ Yes | No |

---

## 🔄 **DOCUMENT LIFECYCLE**

```
Upload → Verification → Approval → Active → Expiry Alert → Renewal → Archive
```

### **Stages:**
1. **Upload** - Employee/HR uploads document
2. **Verification** - HR verifies authenticity
3. **Approval** - Document marked as valid
4. **Active** - Document in use
5. **Expiry Alert** - System sends notification (30 days before)
6. **Renewal** - Employee submits updated document
7. **Archive** - Old document archived for records

---

## 📧 **NOTIFICATIONS**

### **Automatic Alerts:**
- **30 days before expiry** - First reminder
- **15 days before expiry** - Second reminder
- **7 days before expiry** - Urgent reminder
- **On expiry** - Immediate action required

### **Recipients:**
- Employee (email + dashboard notification)
- Reporting Manager
- HR Team
- Admin

---

## 🛡️ **DATA PROTECTION**

### **Security Measures:**
- **Encryption:** All documents encrypted at rest
- **Access Control:** Role-based permissions
- **Audit Logs:** All access tracked
- **Secure Storage:** AWS S3 / Local encrypted storage
- **Backup:** Daily automated backups
- **Retention:** Documents retained as per company policy

### **Privacy Compliance:**
- Adheres to IT Act, 2000
- Follows data minimization principles
- Employee consent recorded
- Right to access and delete (GDPR-like)

---

## 📞 **SUPPORT**

### **For Document Issues:**
- **Email:** hr@nexteons.com
- **Phone:** +91-XXXX-XXXXXX
- **Portal:** HRMS Support Ticket

### **Common Issues:**
- File upload errors
- Document rejection reasons
- Expiry date corrections
- Document replacement requests

---

## 📝 **REVISION HISTORY**

| Version | Date | Changes | Updated By |
|---------|------|---------|------------|
| 1.0 | Feb 5, 2026 | Initial document checklist | HR Team |
| 2.0 | Feb 5, 2026 | Updated to Indian compliance standards | System Admin |

---

**Last Updated:** February 5, 2026  
**Document Owner:** HR Department  
**Review Cycle:** Quarterly  
**Next Review:** May 5, 2026

---

## ✅ **QUICK REFERENCE**

### **Mandatory for ALL Employees:**
1. ✅ Aadhaar Card
2. ✅ PAN Card
3. ✅ Highest Degree/Certificate
4. ✅ Cancelled Cheque / Bank Passbook
5. ✅ EPF Form 11

### **Mandatory for Lateral Hires:**
6. ✅ Relieving Letter
7. ✅ Last 3 Months' Payslips
8. ✅ Form 16 (if mid-year joiner)

### **Conditional:**
9. ⚠️ Final Marksheet (if degree pending)

---

**Note:** This checklist is subject to updates based on regulatory changes and company policies. Always refer to the latest version in the HRMS portal.
