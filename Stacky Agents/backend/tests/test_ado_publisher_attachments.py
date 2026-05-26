from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


def test_publish_from_execution_uploads_and_embeds_attachments(tmp_path, monkeypatch):
    import services.ado_publisher as publisher
    from db import init_db, session_scope
    from models import AgentExecution, Ticket

    monkeypatch.setenv("STACKY_REPO_ROOT", str(tmp_path))
    init_db()

    ado_id = 771234
    out_dir = tmp_path / "Agentes" / "outputs" / str(ado_id)
    attachments_dir = out_dir / "attachments"
    attachments_dir.mkdir(parents=True)
    screenshot = attachments_dir / "final.png"
    screenshot.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    token = "{{ATTACH:QA-UAT-001:final.png}}"
    (out_dir / "comment.html").write_text(
        f"<p>ok</p><img src=\"{token}\" />",
        encoding="utf-8",
    )
    (out_dir / "attachments.json").write_text(
        json.dumps(
            {
                "attachments": [
                    {
                        "token": token,
                        "path": "attachments/final.png",
                        "upload_name": "ADO-771234_final.png",
                        "comment": "QA evidence",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with session_scope() as session:
        ticket = Ticket(
            ado_id=ado_id,
            project="TEST",
            title="Attachment publish",
            ado_state="Active",
        )
        session.add(ticket)
        session.flush()
        execution = AgentExecution(
            ticket_id=ticket.id,
            agent_type="qa-uat",
            status="running",
            started_by="pytest",
            started_at=datetime.utcnow(),
        )
        execution.input_context = []
        session.add(execution)
        session.flush()
        execution_id = execution.id

    class FakeClient:
        def __init__(self):
            self.uploads = []
            self.links = []
            self.comments = []

        def upload_attachment(self, file_path, file_name):
            self.uploads.append((Path(file_path), file_name))
            return {"url": f"https://ado.test/{file_name}"}

        def link_attachment_to_work_item(self, work_item_id, attachment_url, comment=""):
            self.links.append((work_item_id, attachment_url, comment))
            return {"ok": True}

        def post_comment(self, received_ado_id, text, fmt="html"):
            self.comments.append((received_ado_id, text, fmt))
            return {"id": 55}

    fake = FakeClient()

    result = publisher.publish_from_execution(
        execution_id,
        triggered_by="pytest",
        client_factory=lambda: fake,
    )

    assert result.ok is True
    assert len(fake.uploads) == 1
    assert fake.uploads[0][1] == "ADO-771234_final.png"
    assert len(fake.links) == 1
    assert fake.links[0][0] == ado_id
    assert len(fake.comments) == 1
    assert token not in fake.comments[0][1]
    assert "https://ado.test/ADO-771234_final.png" in fake.comments[0][1]
