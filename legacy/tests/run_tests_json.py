import json,unittest
from pathlib import Path
root=Path(__file__).resolve().parents[1]
suite=unittest.defaultTestLoader.discover(str(root/'tests'),pattern='test_*.py')
result=unittest.TextTestRunner(verbosity=2).run(suite)
data={'run':result.testsRun,'passed':result.testsRun-len(result.failures)-len(result.errors)-len(result.skipped),'failures':[(str(t),e) for t,e in result.failures],'errors':[(str(t),e) for t,e in result.errors],'skipped':[(str(t),e) for t,e in result.skipped]}
(root/'outputs/unit_tests.json').write_text(json.dumps(data,indent=2))
raise SystemExit(not result.wasSuccessful())
