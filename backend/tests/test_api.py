"""Tests for FastAPI endpoints."""

import pytest
from fastapi.testclient import TestClient

from main import app


client = TestClient(app)


class TestHealthEndpoints:
    """Test health check endpoints."""

    def test_health(self):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_api_health(self):
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["version"] == "1.0.0"


class TestChatEndpoints:
    """Test chat/query endpoints."""

    def test_chat_query_price(self):
        """Test price query via API."""
        response = client.post(
            "/api/chat/query",
            json={"query": "MX-A01 咖啡灰 18mm 多少钱？"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "answer" in data
        assert "intent" in data
        assert data["intent"] == "query_price"
        assert "318" in data["answer"] or "价格" in data["answer"]

    def test_chat_query_knowledge(self):
        """Test knowledge query via API."""
        response = client.post(
            "/api/chat/query",
            json={"query": "G型拉手安装有什么要求？"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["intent"] == "knowledge"
        assert len(data["answer"]) > 0

    def test_chat_query_empty(self):
        """Test empty query validation."""
        response = client.post(
            "/api/chat/query",
            json={"query": ""},
        )
        assert response.status_code == 422  # Validation error


class TestProductEndpoints:
    """Test product catalog endpoints."""

    def test_list_products(self):
        response = client.get("/api/products")
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "items" in data

    def test_list_products_with_filter(self):
        response = client.get("/api/products?family=饰面门板")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data

    def test_get_product(self):
        # Assuming MX-A01 exists from test fixtures
        response = client.get("/api/products/MX-A01")
        assert response.status_code == 200
        data = response.json()
        assert data["model_no"] == "MX-A01"
        assert "variants" in data

    def test_get_product_not_found(self):
        response = client.get("/api/products/NOT-EXIST")
        assert response.status_code == 404


class TestDocumentEndpoints:
    """Test document upload endpoints."""

    def test_upload_non_pdf(self):
        """Test that only PDF is accepted."""
        response = client.post(
            "/api/documents/upload",
            files={"file": ("test.txt", b"not a pdf", "text/plain")},
        )
        assert response.status_code == 400

    def test_upload_pdf_placeholder(self):
        """Test PDF upload endpoint exists.

        Note: Full PDF processing test requires a real PDF file.
        """
        # Just verify endpoint accepts PDF mime type
        response = client.post(
            "/api/documents/upload",
            files={"file": ("test.pdf", b"%PDF-1.4 fake", "application/pdf")},
        )
        # Will likely fail processing but should not be 400 (bad mime type)
        assert response.status_code != 400
