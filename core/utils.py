import os

def rank_image_upload_to(instance, filename: str) -> str:
    rank_name = (instance.name or "unknown_rank").strip().lower().replace(" ", "_")
    base = os.path.basename(filename)
    return f"system/ranks/{rank_name}/{base}"