import unittest
from core.account_risk_engine import AccountProfile,size_trade

class RiskEngineTests(unittest.TestCase):
    def test_default_budget_uses_drawdown(self):
        self.assertEqual(AccountProfile().risk_budget,40)
    def test_gc_uses_micro_at_2_percent(self):
        d=size_trade("GC",35,AccountProfile())
        self.assertTrue(d["eligible"]);self.assertEqual(d["contract"],"MGC")
    def test_gc_tight_stop_fails_cost_gate(self):
        d=size_trade("GC",31,AccountProfile())
        self.assertEqual(d["status"],"EXECUTION_COST_TOO_HIGH")
    def test_nominal_risk_is_daily_capped(self):
        p=AccountProfile(risk_basis="nominal",risk_percent=1)
        self.assertEqual(p.risk_budget,200)
    def test_nominal_research_budgets_are_exact(self):
        self.assertEqual(AccountProfile(risk_basis="nominal",risk_percent=1,daily_loss_remaining=None).risk_budget,500)
        self.assertEqual(AccountProfile(risk_basis="nominal",risk_percent=2,daily_loss_remaining=None).risk_budget,1000)
        self.assertEqual(AccountProfile(risk_basis="nominal",risk_percent=3,daily_loss_remaining=None).risk_budget,1500)
    def test_tiny_stop_fails_cost_gate(self):
        d=size_trade("CL",5,AccountProfile(risk_percent=3))
        self.assertEqual(d["status"],"EXECUTION_COST_TOO_HIGH")
    def test_personal_bankroll(self):
        p=AccountProfile(risk_basis="personal",personal_bankroll=1500,risk_percent=1,daily_loss_remaining=None)
        self.assertEqual(p.risk_budget,15)

if __name__=="__main__":unittest.main()
