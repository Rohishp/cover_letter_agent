import boto3


S3_BUCKET = "cover-letter-agent"
S3_REGION = "eu-central-1"


def get_s3():
    return boto3.client(
        "s3",
        region_name=S3_REGION,
    )


def save_cover_letter_to_s3(
    run_id: str,
    cover_letter: str,
) -> str:
    """
    Save generated cover letter to S3.

    Returns:
        S3 key
    """

    key = f"cover_letters/{run_id}.txt"

    s3 = get_s3()

    s3.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=cover_letter.encode("utf-8"),
        ContentType="text/plain",
    )

    return key