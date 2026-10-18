from conftest import ROOT
from streamlit.testing.v1 import AppTest

from agent_reliability import __version__


def test_no_key_demo_and_synthetic_failure_view():
    app = AppTest.from_file(str(ROOT / "src/agent_reliability/viewer/app.py")).run(timeout=30)
    assert not app.exception
    assert any(f"ENGINEERING RELEASE {__version__}" in x.value for x in app.caption)
    assert any("Make agent behavior inspectable." in x.value for x in app.title)
    selector = next(x for x in app.selectbox if x.label == "Choose a question")
    selector.select("q002").run(timeout=30)
    assert not app.exception
    assert any("InventedName" in x.value for x in app.error)
    next(x for x in app.button if x.label == "Run the 20-task offline regression").click().run(
        timeout=30
    )
    assert not app.exception
    assert any("Engineering regression gate passed." in x.value for x in app.success)
