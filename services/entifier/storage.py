import asyncio

import boto3
from botocore.config import Config as BotocoreConfig
from botocore.exceptions import ClientError

from config import settings


def _make_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.minio_url,
        aws_access_key_id=settings.minio_access_key,
        aws_secret_access_key=settings.minio_secret_key,
        config=BotocoreConfig(signature_version="s3v4"),
    )


async def ensure_bucket() -> None:
    def _run():
        client = _make_client()
        try:
            client.head_bucket(Bucket=settings.minio_bucket)
        except ClientError:
            client.create_bucket(Bucket=settings.minio_bucket)

    await asyncio.to_thread(_run)


async def upload_file(key: str, content: bytes, content_type: str) -> str:
    def _run():
        client = _make_client()
        client.put_object(
            Bucket=settings.minio_bucket,
            Key=key,
            Body=content,
            ContentType=content_type,
        )

    await asyncio.to_thread(_run)
    return key


async def download_file(key: str) -> bytes:
    def _run():
        client = _make_client()
        response = client.get_object(Bucket=settings.minio_bucket, Key=key)
        return response["Body"].read()

    return await asyncio.to_thread(_run)
