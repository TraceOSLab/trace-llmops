from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from werkzeug.datastructures import FileStorage

from internal.exception import FailException
from internal.service.cos_service import CosService


@pytest.fixture
def upload(monkeypatch):
    records, client = Mock(), Mock()
    service = CosService(records)
    monkeypatch.setattr(service, "_get_client", lambda: client)
    monkeypatch.setattr(service, "_get_bucket", lambda: "test-bucket")
    return service, records, client


@pytest.mark.parametrize("filename,image,expected", [
    ("photo.PNG", True, "photo.PNG"), ("../../报告.txt", False, "报告.txt"),
    (r"C:\fakepath\report.txt", False, "report.txt"),
])
def test_upload_normalizes_extension_and_filename(upload, filename, image, expected):
    service, records, client = upload
    service.upload_file(FileStorage(BytesIO(b"test"), filename=filename), image, SimpleNamespace(id=1))
    assert records.create_upload_file.call_args.kwargs["name"] == expected
    assert records.create_upload_file.call_args.kwargs["extension"] == expected.rsplit(".", 1)[1].lower()
    client.put_object.assert_called_once()


@pytest.mark.parametrize("filename,content", [(None, b"x"), ("bad.exe", b"x"),
    ("x" * 256 + ".txt", b"x"), ("large.txt", b"x" * (15 * 1024 * 1024 + 1))],
    ids=["missing-name", "extension", "long-name", "too-large"])
def test_upload_rejects_invalid_input_before_cos(upload, filename, content):
    service, records, client = upload
    with pytest.raises(FailException):
        service.upload_file(FileStorage(BytesIO(content), filename=filename), False, SimpleNamespace(id=1))
    client.put_object.assert_not_called()
    records.create_upload_file.assert_not_called()


def test_upload_failure_does_not_create_record(upload):
    service, records, client = upload
    client.put_object.side_effect = TimeoutError("secret")
    with pytest.raises(FailException):
        service.upload_file(FileStorage(BytesIO(b"x"), filename="x.txt"), False, SimpleNamespace(id=1))
    records.create_upload_file.assert_not_called()
    client.put_object.assert_called_once()


@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_record_failure_cleans_only_new_object_and_keeps_original_error(upload, cleanup_fails):
    service, records, client = upload
    records.create_upload_file.side_effect = ValueError("database failed")
    if cleanup_fails:
        client.delete_object.side_effect = TimeoutError("secret")
    with pytest.raises(ValueError, match="database failed"):
        service.upload_file(FileStorage(BytesIO(b"x"), filename="x.txt"), False, SimpleNamespace(id=1))
    key = client.put_object.call_args.args[2]
    client.delete_object.assert_called_once_with(Bucket="test-bucket", Key=key)


def test_cos_client_has_timeout_and_no_automatic_retry(monkeypatch):
    config, client = Mock(), Mock()
    monkeypatch.setattr("internal.service.cos_service.CosConfig", config)
    monkeypatch.setattr("internal.service.cos_service.CosS3Client", client)
    CosService._get_client()
    assert config.call_args.kwargs["Timeout"] == 30
    client.assert_called_once_with(config.return_value, retry=0)
