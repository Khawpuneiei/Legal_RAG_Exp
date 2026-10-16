# Fallback positions

Approved alternatives to standard template clauses. Each has a deviation cost set by Legal.
A fallback with deviation cost of 0.5 or more is a **material deviation**: the draft must be routed `escalate` (Senior Legal / Compliance).
A fallback below that threshold may go to standard review. Optional clauses (not fallbacks) carry no deviation cost.

| clause_id | Replaces | Deviation cost | Material? | Used for |
|---|---|---|---|---|
| `BP-DISPUTE-LCIA` | `BP-DISPUTE-SIAC` | 0.7 | yes | Arbitration (London) |
| `BP-GOVLAW-EW` | `BP-GOVLAW-SG` | 0.6 | yes | Governing Law (England and Wales) |
| `DIST-APPOINTMENT-EXCL` | `DIST-APPOINTMENT-NONEXCL` | 0.6 | yes | Exclusive Appointment |
| `BP-LIAB-CAP-FIXED` | `BP-LIAB-CAP-FEES` | 0.5 | yes | Limitation of Liability (Fixed Cap) |
| `IMA-INDEMNITY-MUTUAL` | `IMA-INDEMNITY-CLIENT` | 0.5 | yes | Mutual Indemnity |
| `IMA-LIAB-CAP-FEES` | `IMA-LIAB-GROSS-NEG` | 0.5 | yes | Liability Cap |
| `NDA-CONF-OBLIG-STRICT` | `NDA-CONF-OBLIG` | 0.5 | yes | Confidentiality Obligations (Enhanced) |
| `BP-DISPUTE-SG-COURTS` | `BP-DISPUTE-SIAC` | 0.4 | no | Jurisdiction of the Singapore Courts |
| `BP-TERMINATION-30` | `BP-TERMINATION-90` | 0.4 | no | Termination on Short Notice |
| `DIST-REMUNERATION-FLAT` | `DIST-REMUNERATION-TRAILER` | 0.4 | no | Remuneration (Fixed Fee) |
| `IMA-MGMT-FEE-TIERED` | `IMA-MGMT-FEE` | 0.4 | no | Management Fee (Tiered) |
| `IMA-PERF-FEE-HURDLE` | `IMA-PERF-FEE` | 0.4 | no | Performance Fee (Hurdle) |
| `NDA-TERM-5Y` | `NDA-TERM-2Y` | 0.4 | no | Duration (Extended) |
| `SIDE-MFN-LIMITED` | `SIDE-MFN` | 0.4 | no | Most Favoured Nation (Limited) |
| `SUBS-REDEMPTION-QUARTERLY` | `SUBS-REDEMPTION-MONTHLY` | 0.4 | no | Redemption (Quarterly) |
| `BP-ASSIGNMENT-AFFILIATE` | `BP-ASSIGNMENT-NONE` | 0.3 | no | Assignment to Affiliates |
| `NDA-NON-SOLICIT-6M` | `NDA-NON-SOLICIT-12M` | 0.3 | no | Non-Solicitation (Six Months) |
| `NDA-ONE-WAY-OBLIG` | `NDA-CONF-OBLIG` | 0.3 | no | Confidentiality Obligations (One-Way) |
| `SUBS-INVESTOR-REPS-INSTITUTIONAL` | `SUBS-INVESTOR-REPS-AI` | 0.3 | no | Investor Representations (Institutional) |
| `BP-NOTICES-EMAIL` | `BP-NOTICES` | 0.2 | no | Notices by Email |
| `IMA-REPORTING-QUARTERLY` | `IMA-REPORTING-MONTHLY` | 0.2 | no | Reports (Quarterly) |
| `NDA-MAS-DISCLOSURE` | `NDA-PERMITTED-DISCLOSURE` | 0.2 | no | Disclosure to Regulators |
| `NDA-TERM-3Y` | `NDA-TERM-2Y` | 0.2 | no | Duration (Three Years) |

Legal requirements: some clauses only work together. The renderer adds these automatically, but mention them to the reviewer:

- `BP-DATA-CROSSBORDER` requires `BP-DATA-PDPA`
- `BP-DISPUTE-LCIA` requires `BP-GOVLAW-EW`
- `BP-GOVLAW-EW` requires `BP-DISPUTE-LCIA`
- `BP-LIAB-CAP-FIXED` requires `BP-LIAB-CAP-FEES`
- `DIST-SUB-DISTRIBUTORS` requires `DIST-SELLING-RESTRICTIONS`
- `IMA-KEY-PERSON` requires `DEF-KEY-PERSON`
- `IMA-LIAB-CAP-FEES` requires `IMA-LIAB-GROSS-NEG`
- `IMA-PERF-FEE` requires `DEF-HIGH-WATER-MARK`
- `IMA-PERF-FEE-HURDLE` requires `DEF-HIGH-WATER-MARK`
- `SIDE-FEE-REBATE` requires `DEF-MANAGEMENT-FEE`
- `SIDE-KEY-PERSON-NOTICE` requires `DEF-KEY-PERSON`
- `SIDE-MFN` requires `DEF-SIMILAR-INVESTOR`
- `SIDE-MFN-LIMITED` requires `DEF-SIMILAR-INVESTOR`
