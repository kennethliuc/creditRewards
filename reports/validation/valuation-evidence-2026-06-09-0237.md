# Valuation Verification Report

**Generated:** 2026-06-09 02:37 UTC  
**Aggregation:** typical_utilization  
**Overall:** ✅ valuation_ready

## Agent results

- ✅ **RedemptionEvidence**
- ✅ **ImplementationAuditor**
- ✅ **IndependentVerifier**
- ✅ **RankingStability**
- ✅ **ProductionSmoke**

## CPP table (typical vs legacy max)

| Program | Typical CPP | Legacy max | Δ |
|---------|-------------|------------|---|
| American Express Membership Rewards | 1.47¢ | 2.2¢ | -0.730¢ |
| Chase Ultimate Rewards | 1.3824999999999998¢ | 2.0¢ | -0.618¢ |
| Citi ThankYou Rewards | 1.185¢ | 1.7¢ | -0.515¢ |
| Capital One Miles | 1.2149999999999999¢ | 1.85¢ | -0.635¢ |
| Bilt Points | 1.57¢ | 2.2¢ | -0.630¢ |
| Wells Fargo Go Far Rewards | 1.0¢ | 1.0¢ | +0.000¢ |
| Cash | 1.0¢ | 1.0¢ | +0.000¢ |

## Golden scenarios

| ID | Card | Expected | Actual | Pass |
|----|------|----------|--------|------|
| G01 | amex-gold | $5.88 | $5.88 | ✅ |
| G02 | amex-gold | $1.47 | $1.47 | ✅ |
| G03 | citi-double-cash | $2.37 | $2.37 | ✅ |
| G04 | wells-fargo-active-cash | $2.0 | $2.0 | ✅ |
| G05 | chase-sapphire-preferred | $6.91 | $6.91 | ✅ |

## Ranking stability

| ID | Expected winner | Actual | Pass |
|----|-----------------|--------|------|
| R01 | amex-gold | amex-gold | ✅ |
| R02 | amex-gold | amex-gold | ✅ |
| R03 | citi-doublecash | citi-doublecash | ✅ |

Design: [docs/architecture/points-to-dollar-valuation-report.md](../../docs/architecture/points-to-dollar-valuation-report.md)
Agents: [docs/validation/valuation-multi-agent-system.md](../../docs/validation/valuation-multi-agent-system.md)
