from control_plane import storage


def save_cover_letter(
    run_id: str,
    cover_letter: str,
) -> str:
    """
    Save generated cover letter through the storage layer.

    Returns:
        storage key
    """

    key = f"cover_letters/{run_id}.txt"

    return storage.write_text(key, cover_letter)
