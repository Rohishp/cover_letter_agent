import os
from pathlib import Path


S3_BUCKET_DEFAULT = "cover-letter-agent"
S3_REGION_DEFAULT = "eu-central-1"


def _backend() -> str:
    return os.environ.get("STORAGE_BACKEND", "local")


def _local_root() -> Path:
    return Path(os.environ.get("LOCAL_DATA_DIR", "data"))


def _local_path(key: str) -> Path:
    return _local_root() / key


def _s3_bucket() -> str:
    return os.environ.get("S3_BUCKET", S3_BUCKET_DEFAULT)


def _s3_region() -> str:
    return os.environ.get("AWS_REGION", S3_REGION_DEFAULT)


def _s3_client():
    import boto3

    return boto3.client("s3", region_name=_s3_region())


def read_bytes(key: str) -> bytes:
    if _backend() == "s3":
        client = _s3_client()
        response = client.get_object(Bucket=_s3_bucket(), Key=key)
        return response["Body"].read()

    return _local_path(key).read_bytes()


def read_text(key: str) -> str | None:
    if _backend() == "s3":
        from botocore.exceptions import ClientError

        client = _s3_client()

        try:
            response = client.get_object(Bucket=_s3_bucket(), Key=key)
        except ClientError as error:
            if error.response["Error"]["Code"] in ("NoSuchKey", "404"):
                return None
            raise

        return response["Body"].read().decode("utf-8")

    path = _local_path(key)

    if not path.exists():
        return None

    return path.read_text(encoding="utf-8")


def write_text(key: str, text: str) -> str:
    if _backend() == "s3":
        client = _s3_client()
        client.put_object(Bucket=_s3_bucket(), Key=key, Body=text.encode("utf-8"))
        return key

    path = _local_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return key


def write_bytes(key: str, data: bytes) -> str:
    if _backend() == "s3":
        client = _s3_client()
        client.put_object(Bucket=_s3_bucket(), Key=key, Body=data)
        return key

    path = _local_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return key


def exists(key: str) -> bool:
    if _backend() == "s3":
        from botocore.exceptions import ClientError

        client = _s3_client()

        try:
            client.head_object(Bucket=_s3_bucket(), Key=key)
            return True
        except ClientError as error:
            if error.response["Error"]["Code"] in ("404", "NoSuchKey"):
                return False
            raise

    return _local_path(key).exists()


def list_keys(prefix: str) -> list[str]:
    if _backend() == "s3":
        client = _s3_client()
        response = client.list_objects_v2(Bucket=_s3_bucket(), Prefix=prefix)

        if "Contents" not in response:
            return []

        return [obj["Key"] for obj in response["Contents"]]

    root = _local_root()

    if not root.exists():
        return []

    keys = []

    for path in root.rglob("*"):
        if path.is_file():
            rel = path.relative_to(root).as_posix()

            if rel.startswith(prefix):
                keys.append(rel)

    return sorted(keys)
