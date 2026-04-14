import boto3
import json
from dotenv import load_dotenv
import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

app = FastAPI()
templates = Jinja2Templates(directory="templates")

load_dotenv()

ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://minio:9000")
ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID")
SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
BUCKET = os.getenv("S3_BUCKET_NAME", "freedom-de-projects-s3")

s3 = boto3.client(
    "s3",
    endpoint_url=ENDPOINT,
    aws_access_key_id=ACCESS_KEY,
    aws_secret_access_key=SECRET_KEY,
    region_name="us-east-1"
)

# --- Helper to safely decode corrupted metadata.json files ---
def decode_json_text(content_bytes):
    """Try to fix incorrectly encoded metadata files."""
    try:
        text = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        text = content_bytes.decode("latin-1").encode("utf-8").decode("utf-8")
    return json.loads(text)


def load_metadata_from_s3(project_prefix):
    """Try reading metadata.json from inside the S3 project folder."""
    key = f"{project_prefix.rstrip('/')}/metadata.json"
    try:
        meta_obj = s3.get_object(Bucket=BUCKET, Key=key)
        content = meta_obj["Body"].read()
        return decode_json_text(content)
    except s3.exceptions.NoSuchKey:
        return None
    except Exception:
        # Handle malformed JSON or badly encoded files
        return None


# --- MAIN LOGIC ---
def get_all_projects_directly():
    """Get top-level project folders from S3 and attach metadata."""
    response = s3.list_objects_v2(Bucket=BUCKET, Delimiter="/")
    projects_list = []

    for prefix_info in response.get("CommonPrefixes", []):
        folder_name = prefix_info["Prefix"].strip("/")
        meta = load_metadata_from_s3(prefix_info["Prefix"])

        # Normal project entry
        project_data = {
            "name": meta.get("title", folder_name) if meta else folder_name,
            "author": meta.get("author", "Unknown") if meta else "Unknown",
            "description": meta.get(
                "description",
                "Explore the data pipeline and source code for this data engineering project."
            ) if meta else "Explore the data pipeline and source code for this data engineering project.",
            "tags": meta.get("tags", ["ML", "Dataset"]) if meta else ["ML", "Dataset"],
            "path": prefix_info["Prefix"]
        }
        projects_list.append(project_data)

    # --- Manually add the external Wiki Translator project ---
    projects_list.append({
        "name": "Wiki Translator",
        "author": "Marzhan Sherekhan",
        "description": "A web platform that finds and translates English Wikipedia articles into Kazakh using machine translation.",
        "tags": ["NLP", "Translation", "Web App"],
        "path": "external/wiki-translator",
        "external_url": "https://wikitranslator.sdutechnopark.kz"
    })

    # Wrap in same structure your HTML template expects
    return {"All Projects": projects_list}


def get_contents_at_path(path):
    prefix = path if path.endswith("/") else path + "/"
    response = s3.list_objects_v2(Bucket=BUCKET, Prefix=prefix, Delimiter="/")

    folders = []
    for p in response.get("CommonPrefixes", []):
        folders.append({
            "name": p["Prefix"].replace(prefix, "").strip("/"),
            "path": p["Prefix"]
        })

    files = []
    for obj in response.get("Contents", []):
        key = obj["Key"]
        if key == prefix:
            continue
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": BUCKET, "Key": key},
            ExpiresIn=3600
        )
        files.append({
            "name": os.path.basename(key),
            "url": url
        })

    return folders, files

def get_all_tags(projects_dict):
    """Extract all unique tags from all projects."""
    all_tags = set()
    for student, student_projects in projects_dict.items():
        for project in student_projects:
            for tag in project.get("tags", []):
                all_tags.add(tag)
    return sorted(all_tags)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    projects_data = get_all_projects_directly()
    all_tags = get_all_tags(projects_data)
    
   
    total_count = sum(len(projects_list) for projects_list in projects_data.values())
    
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "projects": projects_data, 
            "all_tags": all_tags, 
            "total_count": total_count 
        }
    )



@app.get("/project/{path:path}", response_class=HTMLResponse)
async def project_page(request: Request, path: str):
    folders, files = get_contents_at_path(path)
    return templates.TemplateResponse(
        request=request,
        name="project.html",
        context={"folders": folders, "files": files, "project": path}
    )

@app.get("/resources", response_class=HTMLResponse)
async def resources_page(request: Request):
    resources_list = [
        {
            "name": "Wikipedia Dumps",
            "description": "Raw data used for training and translation tasks in NLP projects.",
            "url": "https://dumps.wikimedia.org/",
            "category": "Dataset"
        },
        {
            "name": "Kaggle Finance Data",
            "description": "Financial datasets used for banking assistants and stock analysis.",
            "url": "https://www.kaggle.com/datasets",
            "category": "Data Source"
        },
        {
            "name": "Hugging Face Hub",
            "description": "Pre-trained models and specialized NLP datasets.",
            "url": "https://huggingface.co/datasets",
            "category": "ML Hub"
        }
    ]
    return templates.TemplateResponse(
        "resources.html", 
        {"request": request, "resources": resources_list}
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=80)
