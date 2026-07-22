import json
import boto3
import pyperclip


lambda_client = boto3.client(
    "lambda",
    region_name="eu-central-1",
)


FUNCTION_NAME = "cover-letter-agent"


def read_clipboard_windows() -> str:
    """
    Read JD from local clipboard.
    """

    text = pyperclip.paste()

    if not text or not text.strip():
        raise ValueError(
            "Clipboard is empty. Copy the complete job description first."
        )

    return text.strip()



def invoke_pipeline():

    jd_text = read_clipboard_windows()

    response = lambda_client.invoke(
        FunctionName=FUNCTION_NAME,
        InvocationType="RequestResponse",
        Payload=json.dumps(
            {
                "jd_text": jd_text,
                "cv_path": "resume/Rohish_Resume.pdf",
            }
        ).encode("utf-8"),
    )

    result = json.loads(
        response["Payload"]
        .read()
        .decode("utf-8")
    )

    print(result)



if __name__ == "__main__":
    invoke_pipeline()