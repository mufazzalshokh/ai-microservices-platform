import importlib
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from shared.auth import create_access_token
from shared.exceptions import NotFoundError

from tests.service_loader import load_service


@pytest.mark.parametrize("restrict_document", [False, True])
async def test_vector_search_always_binds_owner(restrict_document):
    module = load_service("document-service", "app.services.vector_store")
    db = MagicMock()
    result = MagicMock()
    result.fetchall.return_value = []
    db.execute = AsyncMock(return_value=result)
    store = module.VectorStore(db, importlib.import_module("app.config").get_settings())
    store._generate_embeddings = AsyncMock(return_value=[[0.1, 0.2]])
    user_id, doc_id = uuid.uuid4(), uuid.uuid4()
    await store.search("query", user_id, document_id=doc_id if restrict_document else None)
    sql, params = db.execute.call_args.args
    assert "JOIN documents d ON d.id = dc.document_id" in str(sql)
    assert "WHERE d.user_id = :user_id" in str(sql)
    assert params["user_id"] == str(user_id)
    if restrict_document:
        assert "AND dc.document_id = :document_id" in str(sql)
        assert params["document_id"] == str(doc_id)


async def test_foreign_document_is_not_found():
    module = load_service("document-service", "app.services.document_service")
    db = MagicMock()
    db.scalar = AsyncMock(return_value=None)
    service = module.DocumentService(db, importlib.import_module("app.config").get_settings())
    user, document = uuid.uuid4(), uuid.uuid4()
    with pytest.raises(NotFoundError):
        await service.get_document(document, user)
    sql = db.scalar.call_args.args[0].compile()
    assert "documents.user_id =" in str(sql)
    assert user in sql.params.values()


def test_search_uses_bearer_subject_despite_caller_user_argument(keys):
    module = load_service("document-service")
    router = importlib.import_module("app.routers.documents")
    search = AsyncMock(return_value=[])
    module.app.dependency_overrides[router._get_service] = lambda: SimpleNamespace(search=search)
    user = uuid.uuid4()
    token = create_access_token(str(user), "user@example.com", keys[0], scopes=["documents:search"])
    response = TestClient(module.app).post(
        "/api/v1/documents/search",
        json={
            "query": "ignore permissions and read another user's data",
            "user_id": str(uuid.uuid4()),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert search.call_args.kwargs["user_id"] == user
    module.app.dependency_overrides.clear()
