from pathlib import Path
import sys
from absl import flags
from absl.testing import absltest
flags.FLAGS(['tests'])
Path(absltest.TEST_TMPDIR.value).mkdir(parents=True, exist_ok=True)
sys.path.insert(0,str(Path.cwd()))
import pytest
raise SystemExit(pytest.main(sys.argv[1:]))
