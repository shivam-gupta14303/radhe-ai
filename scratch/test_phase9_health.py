import sys
from pathlib import Path
import unittest
import tempfile

# Ensure src/ is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from health_assistant import HealthAssistant
from command_parser import parser
from command_executor import CommandExecutor
from backend_api import (
    log_health_vital, log_water_intake, get_water_intake,
    get_daily_health_summary, add_medication, list_medications,
    log_medication_taken, triage_symptoms,
    VitalLogRequest, WaterLogRequest, MedicationAddRequest,
    MedicationTakenRequest, SymptomTriageRequest
)

class TestPhase9Health(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_health.db"
        self.ha = HealthAssistant(db_path=self.db_path)
        self.executor = CommandExecutor()

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_vitals_logging_and_summary(self):
        # 1. Log water
        tot1, msg1 = self.ha.log_water(500.0)
        self.assertEqual(tot1, 500.0)
        self.assertIn("Logged 500ml water", msg1)

        tot2, _ = self.ha.log_water(300.0)
        self.assertEqual(tot2, 800.0)

        # 2. Log other vitals
        self.ha.log_vital("systolic", 120, unit="mmHg")
        self.ha.log_vital("diastolic", 80, unit="mmHg")
        self.ha.log_vital("glucose", 95, unit="mg/dL")
        self.ha.log_vital("sleep", 7.5, unit="hours")

        # 3. Daily summary
        summary = self.ha.get_daily_vitals_summary()
        self.assertEqual(summary["water_ml"], 800.0)
        self.assertEqual(summary["blood_pressure"], "120/80 mmHg")
        self.assertEqual(summary["glucose"], 95.0)
        self.assertEqual(summary["sleep_hours"], 7.5)

    def test_medication_adherence(self):
        # 1. Add medication
        mid = self.ha.add_medication(
            name="Metformin",
            dosage="500mg",
            schedule_time="09:00",
            instructions="After breakfast",
            remaining_doses=6
        )
        self.assertIsInstance(mid, int)

        # 2. List medications
        meds = self.ha.list_medications(active_only=True)
        self.assertEqual(len(meds), 1)
        self.assertEqual(meds[0]["name"], "Metformin")
        self.assertEqual(meds[0]["remaining_doses"], 6)

        # 3. Take dose (remaining goes from 6 to 5 -> triggers refill alert!)
        ok, msg = self.ha.log_medication_taken("Metformin")
        self.assertTrue(ok)
        self.assertIn("Refill Alert", msg)

        meds_after = self.ha.list_medications(active_only=True)
        self.assertEqual(meds_after[0]["remaining_doses"], 5)

    def test_symptom_triage_safety_guardrails(self):
        # 1. Routine symptom
        res1 = self.ha.triage_symptoms("I have a mild headache and fatigue", language="en")
        self.assertFalse(res1["is_emergency"])
        self.assertEqual(res1["urgency"], "routine")
        self.assertIn("Disclaimer: I am an AI companion", res1["disclaimer"])
        self.assertTrue(any(h["number"] == "112" for h in res1["hotlines"]))

        # 2. Emergency red flag
        res2 = self.ha.triage_symptoms("Sudden severe chest pain and difficulty breathing", language="en")
        self.assertTrue(res2["is_emergency"])
        self.assertEqual(res2["urgency"], "critical")
        self.assertIn("CRITICAL HEALTH ALERT", res2["message"])

        # 3. Hindi disclaimer
        res3 = self.ha.triage_symptoms("Gala kharab hai", language="hi")
        self.assertIn("doctor nahi", res3["disclaimer"])

    def test_voice_parser_and_executor(self):
        # 1. Log water
        cmd1 = parser.parse("drank 500 ml water")
        self.assertEqual(cmd1.get("intent"), "log_water_intake")
        r1 = self.executor.execute(cmd1, "drank 500 ml water")
        self.assertIn("Logged 500ml water", r1.get("response", ""))

        # 2. Water status
        cmd2 = parser.parse("how much water did i drink")
        self.assertEqual(cmd2.get("intent"), "get_water_intake")
        r2 = self.executor.execute(cmd2, "how much water did i drink")
        self.assertIn("consumed", r2.get("response", ""))

        # 3. Log blood pressure
        cmd3 = parser.parse("log blood pressure 120 over 80")
        self.assertEqual(cmd3.get("intent"), "log_vital_sign")
        r3 = self.executor.execute(cmd3, "log blood pressure 120 over 80")
        self.assertIn("120/80 mmHg", r3.get("response", ""))

        # 4. List medicines
        cmd4 = parser.parse("what medicines do i have")
        self.assertEqual(cmd4.get("intent"), "list_medications")
        r4 = self.executor.execute(cmd4, "what medicines do i have")
        self.assertIn("medication", r4.get("response", "").lower())

    def test_fastapi_health_endpoints(self):
        # 1. Log water endpoint
        w_res = log_water_intake(WaterLogRequest(amount_ml=400.0))
        self.assertTrue(w_res["success"])

        # 2. Get water endpoint
        gw_res = get_water_intake()
        self.assertGreaterEqual(gw_res["today_total_ml"], 400.0)

        # 3. Log vital endpoint
        v_res = log_health_vital(VitalLogRequest(metric="sleep", value=8.0, unit="hours"))
        self.assertTrue(v_res["success"])

        # 4. Add medication endpoint
        m_res = add_medication(MedicationAddRequest(
            name="Vitamin D", dosage="1000 IU", schedule_time="10:00", instructions="With milk"
        ))
        self.assertTrue(m_res["success"])

        # 5. List medications endpoint
        lm_res = list_medications(active_only=True)
        self.assertTrue(any(m["name"] == "Vitamin D" for m in lm_res))

        # 6. Symptom triage endpoint
        t_res = triage_symptoms(SymptomTriageRequest(symptoms="Chest pain and dizziness"))
        self.assertTrue(t_res["is_emergency"])
        self.assertEqual(t_res["urgency"], "critical")

if __name__ == "__main__":
    unittest.main()
