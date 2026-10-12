"""Write-once object stores: a local directory (dev, tests) and Cloudflare R2 through its S3 API (v1 profile).

Both share put / get / keys / delete. put never overwrites: replacing an object is an explicit delete + put.
"""

from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from core.secrets import load_secret


class ObjectExists(FileExistsError):
    pass


class LocalStore:
    def __init__(self, root):
        self.root = Path(root).resolve()

    def _path(self, key):
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root) or path == self.root:
            raise ValueError(f"invalid key: {key!r}")
        return path

    def put(self, key, data):
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("xb") as file:
                file.write(data)
        except FileExistsError:
            raise ObjectExists(key) from None

    def get(self, key):
        try:
            return self._path(key).read_bytes()
        except FileNotFoundError:
            raise KeyError(key) from None

    def keys(self, prefix=""):
        found = (p.relative_to(self.root).as_posix() for p in self.root.rglob("*") if p.is_file())
        return sorted(k for k in found if k.startswith(prefix))

    def delete(self, key):
        self._path(key).unlink(missing_ok=True)


class R2Store:
    def __init__(self, bucket, client):
        self.bucket, self.client = bucket, client

    def put(self, key, data):
        try:
            self.client.put_object(Bucket=self.bucket, Key=key, Body=data, IfNoneMatch="*")
        except ClientError as error:
            if error.response["Error"]["Code"] in ("PreconditionFailed", "412"):
                raise ObjectExists(key) from None
            raise

    def get(self, key):
        try:
            return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except ClientError as error:
            if error.response["Error"]["Code"] in ("NoSuchKey", "404"):
                raise KeyError(key) from None
            raise

    def keys(self, prefix=""):
        pages = self.client.get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix=prefix)
        return sorted(item["Key"] for page in pages for item in page.get("Contents", []))

    def delete(self, key):
        self.client.delete_object(Bucket=self.bucket, Key=key)


def r2_store_from_secrets():
    client = boto3.client(
        "s3",
        endpoint_url=f"https://{load_secret('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com",
        aws_access_key_id=load_secret("R2_ACCESS_KEY_ID"),
        aws_secret_access_key=load_secret("R2_SECRET_ACCESS_KEY"),
        region_name="auto",
    )
    return R2Store(load_secret("R2_BUCKET"), client)
